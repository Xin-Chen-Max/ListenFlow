"""Private proxy boundaries and body limits; all data is isolated."""
import asyncio
import time
import pytest
from fastapi.testclient import TestClient
import app as server
import access

ORIGIN = "https://listenflow.example.ts.net"
OWNER = "owner@example.com"


@pytest.fixture
def base_client(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRARY_DB", str(tmp_path / "library.db"))
    monkeypatch.setenv("LISTENFLOW_MODE", "local")
    monkeypatch.delenv("LISTENFLOW_PRIVATE_USER", raising=False)
    monkeypatch.delenv("LISTENFLOW_PRIVATE_ORIGIN", raising=False)
    for name in ("UPLOADS", "OUTPUT"):
        folder = tmp_path / name.lower()
        folder.mkdir()
        monkeypatch.setattr(server, name, folder)
    monkeypatch.setattr(server, "JOBS", {})
    async def loopback(scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope, client=("127.0.0.1", 12345))
        await server.app(scope, receive, send)
    return loopback


def private(monkeypatch):
    monkeypatch.setenv("LISTENFLOW_MODE", "private")
    monkeypatch.setenv("LISTENFLOW_PRIVATE_USER", OWNER)
    monkeypatch.setenv("LISTENFLOW_PRIVATE_ORIGIN", ORIGIN)


def test_local_mode(base_client):
    with TestClient(base_client) as c:
        assert c.get("/api/connection").json()["mode"] == "local"
        assert c.get("/api/library").status_code == 200
        assert c.get("/", headers={"Tailscale-User-Login": OWNER}).status_code == 403


@pytest.mark.parametrize("setting,value", [("LISTENFLOW_MODE", "privtae"), ("LISTENFLOW_PRIVATE_USER", ""),
    ("LISTENFLOW_PRIVATE_ORIGIN", ""), ("LISTENFLOW_PRIVATE_ORIGIN", "http://pc.example.ts.net"),
    ("LISTENFLOW_PRIVATE_ORIGIN", "https://pc.example.com")])
def test_misconfiguration_fails_closed(base_client, monkeypatch, setting, value):
    private(monkeypatch)
    monkeypatch.setenv(setting, value)
    with TestClient(base_client, base_url=ORIGIN) as c:
        assert c.get("/", headers={"Tailscale-User-Login": OWNER}).status_code == 503


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/docs", "/openapi.json", "/api/library",
    "/api/uploads/abc", "/api/library/abc/media", "/api/jobs/abc/events", "/api/jobs/abc/download/txt", "/api/ai/status"])
def test_all_routes_require_identity(base_client, monkeypatch, path):
    private(monkeypatch)
    with TestClient(base_client, base_url=ORIGIN) as c:
        assert c.get(path).status_code == 401
        assert c.get(path, headers={"Tailscale-User-Login": "stranger@example.com"}).status_code == 403


def test_owner_native_and_browser_and_host(base_client, monkeypatch):
    private(monkeypatch)
    headers = {"Tailscale-User-Login": "OWNER@example.com"}
    with TestClient(base_client, base_url=ORIGIN) as c:
        assert c.get("/api/connection", headers=headers).json()["user"] == "OWNER@example.com"
        assert c.get("/", headers={**headers, "Origin": ORIGIN}).status_code == 200
        for origin in ["null", "https://evil.example"]:
            assert c.post("/api/jobs", headers={**headers,"Origin":origin}).status_code == 403
        assert c.get("/", headers={**headers,"Host":"localhost:8765"}).status_code == 403


def test_proxy_peer_and_prebody_checks(monkeypatch):
    private(monkeypatch)
    async def exercise(peer, headers, expected, method="POST", path="/api/jobs"):
        touched = False
        sent = []
        async def downstream(scope, receive, send):
            nonlocal touched
            touched = True
            raise AssertionError("Unauthenticated request reached parser")
        async def receive():
            raise AssertionError("Rejected request body was read")
        async def send(message): sent.append(message)
        await access.AccessControlMiddleware(downstream)({"type":"http","method":method,"path":path,
            "client":(peer,123),"headers":headers},receive,send)
        assert sent[0]["status"] == expected and not touched
    headers=[(b"host",b"listenflow.example.ts.net"),(b"tailscale-user-login",OWNER.encode())]
    asyncio.run(exercise("192.168.1.20", headers,403))
    asyncio.run(exercise("127.0.0.1", [(b"host",b"localhost")],401))
    asyncio.run(exercise("127.0.0.1", headers+[(b"tailscale-user-login",b"other")],400))
    asyncio.run(exercise("127.0.0.1", headers+[(b"content-length",b"99999999999")],413))


@pytest.mark.parametrize("length", ["-1","invalid"])
def test_invalid_content_length(base_client, length):
    with TestClient(base_client) as c:
        assert c.post("/api/jobs",headers={"Content-Length":length}).status_code == 400


def test_unknown_length_stream_is_limited_and_parser_files_closed(base_client, monkeypatch):
    monkeypatch.setenv("LISTENFLOW_MAX_UPLOAD_BYTES", "2")
    with TestClient(base_client) as c:
        response=c.post("/api/export/docx", content=iter([b"abc",b"def"]), headers={"Content-Type":"application/json"})
        assert response.status_code == 413
        assert c.post("/api/jobs",files={"file":("x.wav",b"1234","audio/wav")}).status_code == 413
        assert list(server.UPLOADS.iterdir()) == []


def test_second_process_lock_does_not_interrupt_jobs(base_client):
    import library
    from process_lock import library_lock
    with TestClient(base_client):
        library.add("running", "active.wav", [], status="running")
        with pytest.raises(RuntimeError, match="Another ListenFlow process"):
            with library_lock():
                pass
        assert library.get("running")["status"] == "running"


def test_streaming_heartbeat_comments(base_client, monkeypatch):
    import threading
    monkeypatch.setenv("LISTENFLOW_HEARTBEAT_SEC", "0.05")
    job_id = "heartbeat_test"
    server.JOBS[job_id] = {
        "status": "running",
        "name": "test.wav",
        "segments": [],
        "duration": 0.0,
        "stem": "test",
        "events": [],
        "finished": False,
        "_media_path": None,
        "_model": "tiny",
        "_lang": "en",
        "_diarize": False,
    }

    with TestClient(base_client) as client:
        def finish_later():
            time.sleep(0.2)
            server.JOBS[job_id]["finished"] = True

        finisher = threading.Thread(target=finish_later, daemon=True)
        finisher.start()

        res = client.get(f"/api/jobs/{job_id}/events")
        assert res.status_code == 200
        text = res.text
        assert ": heartbeat\n\n" in text
        assert "event: end\ndata: {}\n\n" in text
