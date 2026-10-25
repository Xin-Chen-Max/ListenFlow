"""Persistence and failure regressions using isolated storage and a stub ASR.

Real GPU inference is covered separately by scripts/validate_local.py.
"""

import io
import json
import queue
import sqlite3
import wave

import pytest
from fastapi.testclient import TestClient

import app as server
import library


SEGMENTS = [
    {"start": 0.0, "end": 1.0, "text": "Did you get it?", "words": [
        {"start": 0.0, "end": .3, "word": " Did"},
        {"start": .3, "end": .5, "word": " you"},
        {"start": .5, "end": .8, "word": " get"},
        {"start": .8, "end": 1.0, "word": " it?"}]},
    {"start": 1.0, "end": 2.0, "text": "I want to listen again.", "words": []},
]


def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 32000)
    return out.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DB", str(tmp_path / "library.db"))
    for name in ("UPLOADS", "OUTPUT"):
        folder = tmp_path / name.lower()
        folder.mkdir()
        monkeypatch.setattr(server, name, folder)
    monkeypatch.setattr(server, "JOBS", {})
    monkeypatch.setattr(server, "_pending", queue.Queue())

    def fake_transcribe(*args, **kwargs):
        yield {"type": "language", "language": "en", "probability": 1.0}
        yield {"type": "done", "segments": json.loads(json.dumps(SEGMENTS)), "duration": 2.0}

    monkeypatch.setattr(server.core, "transcribe", fake_transcribe)
    with TestClient(server.app) as c:
        yield c


def create(client, run=True, filename="recording.wav"):
    response = client.post("/api/jobs", files={"file": (filename, wav_bytes(), "audio/wav")},
                           data={"model": "tiny", "language": "en"})
    assert response.status_code == 200, response.text
    id = response.json()["job_id"]
    if run:
        job = server.JOBS[id]
        server._run_job(id, job["_media_path"], "tiny", "en")
    return id


def test_retained_audio_reopens_and_deletes_after_restart(client):
    id = create(client)
    item = client.get(f"/api/library/{id}").json()
    assert item["status"] == "done" and "media_path" not in item
    assert item["segments"][0]["words"]
    assert client.get(item["media_url"]).content == wav_bytes()
    response = client.get(item["media_url"], headers={"Range": "bytes=0-31"})
    assert response.status_code == 206 and len(response.content) == 32
    assert client.post(f"/api/library/{id}/clips", json={"segment_index": 0}).status_code == 200
    server.JOBS.clear()  # Simulate losing all in-memory state.
    reopened = client.get(f"/api/library/{id}").json()
    assert reopened["clips"] and reopened["media_url"]
    assert "Did you" in client.get(f"/api/jobs/{id}/download/txt").text
    assert client.get(f"/api/jobs/{id}/download/srt").text.startswith("1\n00:00:00,000")
    for _ in range(2):  # Event streams must be replayable, not destructive queue reads.
        events = client.get(f"/api/jobs/{id}/events").text
        assert '"type": "done"' in events and "event: end" in events
    assert client.delete(f"/api/library/{id}").json() == {"ok": True}
    assert client.get(reopened["media_url"]).status_code == 404
    assert not (server.UPLOADS / id).exists()
    assert not (server.OUTPUT / id).exists()
    assert library.count() == 0
    conn = library._connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 0
    finally:
        conn.close()


def test_edits_persist_clear_stale_word_alignment_and_update_exports(client):
    id = create(client)
    response = client.patch(f"/api/library/{id}", json={"texts": ["Corrected sentence.", SEGMENTS[1]["text"]]})
    assert response.status_code == 200
    server.JOBS.clear()
    item = client.get(f"/api/library/{id}").json()
    assert item["segments"][0]["text"] == "Corrected sentence."
    assert item["segments"][0]["words"] == []
    assert item["segments"][0]["end"] == 1.0
    assert "Corrected sentence." in client.get(f"/api/jobs/{id}/download/txt").text
    assert "Corrected sentence." in next((server.OUTPUT / id).glob("*.srt")).read_text()
    assert client.patch(f"/api/library/{id}", json={"texts": []}).status_code == 409


def test_patterns_endpoint_explains_text_candidates_only(client):
    id = create(client)
    data = client.get(f"/api/library/{id}/patterns").json()
    patterns = data["patterns"]
    assert {(p["phrase"], p["rule_id"]) for p in patterns} == {
        ("Did you", "assimilation.yod"), ("get it", "consonant.flap"), ("get it", "linking.c_v"),
        ("want to", "elision.cluster_td"), ("want to", "reduction.function_word"), ("listen again", "linking.c_v")}
    assert all(p["label"] == "Possible pattern" and p["evidence"] == "text-rule" for p in patterns)
    assert all(p["status"] in {"candidate", "uncertain"} and p["confidence"] is None for p in patterns)
    assert all(p["source_audio"] == f"/api/library/{id}/media" for p in patterns)
    assert data["schema_version"] == "1.0" and data["capabilities"]["acoustically_verified"] == []
    assert data["transcript_fingerprint"] == client.get(f"/api/library/{id}").json()["transcript_fingerprint"]
    assert data["coverage"]["token_count"] == 9
    assert (patterns[0]["start"], patterns[0]["end"], patterns[0]["timing"]) == (0, .5, "words")


def test_patterns_are_derived_after_edits_with_legacy_audio_and_missing_ids(client):
    library.add("legacy", "Old.wav", SEGMENTS)
    before = client.get("/api/library/legacy/patterns").json()
    assert all(p["source_audio"] is None for p in before["patterns"])
    assert client.patch("/api/library/legacy", json={"texts": ["Need it. Turn off. See it. Did you want to?", "zzqxunknown"]}).status_code == 200
    after = client.get("/api/library/legacy/patterns").json()
    assert before["transcript_fingerprint"] != after["transcript_fingerprint"]
    assert {"linking.c_v", "linking.v_v", "assimilation.yod", "reduction.function_word"} <= {p["rule_id"] for p in after["patterns"]}
    assert all(p["timing"] == "segment" for p in after["patterns"])
    assert any(d["reason"] == "unknown_word" for d in after["coverage"]["diagnostics"])
    assert client.get("/api/library/missing/patterns").status_code == 404


def test_dictionary_analysis_runs_outside_event_loop(client, monkeypatch):
    import asyncio
    import speech_patterns
    original = speech_patterns.analyze
    called = []

    def inspect(*args, **kwargs):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        called.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(speech_patterns, "analyze", inspect)
    id = create(client)
    assert client.get(f"/api/library/{id}/patterns").status_code == 200
    assert called == [True]


def test_bounded_patterns_api_rejects_stale_transcripts_and_invalid_limits(client):
    id = create(client)
    item = client.get(f"/api/library/{id}").json()
    url = f"/api/library/{id}/patterns"
    result = client.get(url, params={"view": "summary", "segment_start": 1, "segment_limit": 1,
                                      "fingerprint": item["transcript_fingerprint"]})
    assert result.status_code == 200
    data = result.json()
    assert data["range"] == {"segment_start": 1, "segment_end": 2, "total_segments": 2}
    assert all(1 in p["segment_indices"] and "pronunciations" not in p for p in data["patterns"])
    assert client.get(url, params={"fingerprint": "old"}).status_code == 409
    for params in ({"segment_limit": 49}, {"segment_start": -1}, {"view": "other"}):
        assert client.get(url, params=params).status_code == 422


def test_subtitle_timestamp_rounding_carries_minutes_and_hours():
    assert server.core._ts(59.9996) == "00:01:00,000"
    assert server.core._ts(3599.9996) == "01:00:00,000"
    assert server.core._ts(-1) == "00:00:00,000"


def test_failure_retains_audio_and_retry_works(client, monkeypatch):
    id = create(client, run=False)
    def failure(*args, **kwargs):
        yield {"type": "error", "message": "Model could not load."}
    monkeypatch.setattr(server.core, "transcribe", failure)
    server._run_job(id, server.JOBS[id]["_media_path"], "tiny", "en")
    server.JOBS.clear()
    item = client.get(f"/api/library/{id}").json()
    assert item["status"] == "error" and "Model could not load" in item["error"]
    assert client.get(item["media_url"]).status_code == 200
    assert client.post(f"/api/jobs/{id}/retry").status_code == 200
    assert client.post(f"/api/jobs/{id}/retry").status_code == 409
    assert client.delete(f"/api/library/{id}").status_code == 409


def test_interrupted_job_is_recoverable(client):
    id = create(client, run=False)
    library.interrupt_pending()
    server.JOBS.clear()
    assert "interrupted" in client.get(f"/api/library/{id}").json()["error"]
    events = client.get(f"/api/jobs/{id}/events", headers={"Last-Event-ID": "9"}).text
    assert '"type": "error"' in events and "interrupted" in events
    assert client.post(f"/api/jobs/{id}/retry").status_code == 200


def test_windows_file_lock_is_retried_without_losing_library_state(client, monkeypatch):
    id = create(client)
    original = server.shutil.rmtree
    attempts = []
    def busy_once(path, *args, **kwargs):
        attempts.append(path)
        if len(attempts) == 1:
            raise PermissionError("Playback still has the file open")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(server.shutil, "rmtree", busy_once)
    assert client.delete(f"/api/library/{id}").status_code == 200
    assert len(attempts) >= 2 and library.get(id) is None


def test_busy_file_returns_actionable_error_and_keeps_record(client, monkeypatch):
    id = create(client)
    def busy(*args, **kwargs):
        raise PermissionError("Busy")
    monkeypatch.setattr(server.shutil, "rmtree", busy)
    response = client.delete(f"/api/library/{id}")
    assert response.status_code == 409 and "Close playback" in response.json()["detail"]
    assert library.get(id) is not None


def test_legacy_items_have_no_audio_and_bad_paths_are_not_served(client):
    library.add("legacy", "Old.wav", SEGMENTS)
    assert client.get("/api/library/legacy").json()["media_url"] is None
    assert client.get("/api/library/legacy/media").status_code == 404
    library.add("bad", "Unsafe.wav", SEGMENTS, media_path="../../private.wav")
    assert client.get("/api/library/bad/media").status_code == 400


def test_clip_save_is_idempotent_and_removal_is_scoped(client):
    id = create(client)
    first = client.post(f"/api/library/{id}/clips", json={"segment_index": 0}).json()
    second = client.post(f"/api/library/{id}/clips", json={"segment_index": 0}).json()
    assert first["id"] == second["id"]
    assert client.post(f"/api/library/{id}/clips", json={"segment_index": -1}).status_code == 400
    assert client.delete(f"/api/library/wrong/clips/{first['id']}").status_code == 404
    assert client.delete(f"/api/library/{id}/clips/{first['id']}").status_code == 200


def test_nonmedia_empty_and_pathlike_upload_names(client):
    assert client.post("/api/jobs", files={"file": ("a.txt", b"text")}).status_code == 400
    assert client.post("/api/jobs", files={"file": ("a.wav", b"")}).status_code == 400
    id = create(client, filename="../../outside.wav")
    assert library.get(id)["name"] == "outside.wav"
    assert (server.UPLOADS / id / "source.wav").is_file()


def test_migration_preserves_old_transcripts(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE transcripts (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL, duration REAL DEFAULT 0, language TEXT DEFAULT '', model TEXT DEFAULT '', source TEXT DEFAULT '', text TEXT NOT NULL, segments TEXT NOT NULL)")
    conn.execute("INSERT INTO transcripts VALUES ('old','old.wav',1,2,'en','tiny','app','Hello','[]')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("LIBRARY_DB", str(db))
    item = library.get("old")
    assert item["name"] == "old.wav" and item["status"] == "done"
    assert item["media_path"] == "" and item["clips"] == []
