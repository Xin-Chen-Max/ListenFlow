"""Durable upload contracts and crash windows; no user data or GPU jobs."""
import os
import queue
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
import app as server
import library
from uploads import UploadStore, EXPIRY_SECONDS


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DB",str(tmp_path/"library.db"))
    monkeypatch.setenv("LISTENFLOW_MODE","local")
    for name in ("UPLOADS","OUTPUT"):
        path=tmp_path/name.lower();path.mkdir();monkeypatch.setattr(server,name,path)
    monkeypatch.setattr(server,"JOBS",{})
    monkeypatch.setattr(server,"_pending",queue.Queue())
    with TestClient(server.app) as c:
        yield c


def create(client, data=b"recording", **kwargs):
    body={"client_id":str(uuid.uuid4()),"name":"lecture.m4a","length":len(data),"model":"tiny","language":"en",**kwargs}
    response=client.post("/api/uploads",json=body)
    assert response.status_code==200,response.text
    return response.json()["id"],body


def patch(client,id,offset,data):
    return client.patch(f"/api/uploads/{id}",headers={"Upload-Offset":str(offset),"Content-Type":"application/octet-stream"},content=data)


def test_resume_lost_ack_complete_once_and_deleted_stays_deleted(client):
    id,body=create(client)
    assert client.post("/api/uploads",json=body).json()["id"]==id
    assert patch(client,id,0,b"record").status_code==204
    assert patch(client,id,0,b"record").status_code==409
    assert client.head(f"/api/uploads/{id}").headers["Upload-Offset"]=="6"
    assert patch(client,id,6,b"ing").status_code==204
    for _ in range(2):
        assert client.post(f"/api/uploads/{id}/complete").json()["job_id"]==id
    assert library.count()==1 and server._pending.qsize()==1
    assert client.get(f"/api/library/{id}/media").content==b"recording"
    assert client.head(f"/api/uploads/{id}").headers["Upload-Job-Id"]==id
    server.JOBS.clear()
    library.set_status(id,"done")
    assert client.delete(f"/api/library/{id}").status_code==200
    assert client.post(f"/api/uploads/{id}/complete").json()["deleted"] is True
    assert library.get(id) is None
    assert client.post("/api/uploads",json=body).status_code==410
    with UploadStore(server.UPLOADS).connect() as conn:
        row=conn.execute("SELECT * FROM upload_sessions WHERE id=?",(id,)).fetchone()
        assert row["name"]=="" and row["length"]==0 and row["model"]==""


def test_uncommitted_tail_and_move_before_commit_recovered(client):
    id,_=create(client)
    assert patch(client,id,0,b"recording").status_code==204
    store=UploadStore(server.UPLOADS)
    with store.part(id).open("ab") as f:f.write(b"uncommitted tail")
    assert client.head(f"/api/uploads/{id}").headers["Upload-Offset"]=="9"
    assert store.part(id).read_bytes()==b"recording"
    with store.connect() as conn: row=store.row(conn,id,"local")
    dest=store.destination(row);dest.parent.mkdir();os.replace(store.part(id),dest)
    server.JOBS.clear()
    assert client.head(f"/api/uploads/{id}").status_code==200
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _:UploadStore(server.UPLOADS).complete(id,"local"), range(2)))==[id,id]
    assert library.count()==1
    assert client.post(f"/api/uploads/{id}/complete").json()["job_id"]==id
    assert server._pending.qsize()==1


def test_limits_validation_and_offsets(client,monkeypatch):
    id,body=create(client)
    assert patch(client,id,-1,b"a").status_code==400
    assert patch(client,id,1,b"a").headers["Upload-Offset"]=="0"
    assert patch(client,id,0,b"too long recording").status_code==413
    assert patch(client,id,0,b"").status_code==413
    assert client.post(f"/api/uploads/{id}/complete").status_code==409
    assert client.post("/api/uploads",json={**body,"length":20}).status_code==409
    assert client.post("/api/uploads",json={**body,"model":"nonsense"}).status_code==400
    assert client.post("/api/uploads",json={**body,"length":1.5}).status_code==422
    monkeypatch.setenv("LISTENFLOW_MAX_UPLOAD_BYTES","3")
    assert client.post("/api/uploads",json={**body,"client_id":str(uuid.uuid4())}).status_code==413


def test_cancel_expiry_and_ownership(client):
    store=UploadStore(server.UPLOADS)
    id,_=create(client)
    assert patch(client,id,0,b"record").status_code==204
    with pytest.raises(HTTPException) as e:store.status(id,"stranger")
    assert e.value.status_code==404
    assert client.delete(f"/api/uploads/{id}").status_code==204
    assert not store.part(id).exists()
    assert client.head(f"/api/uploads/{id}").status_code==410
    id,_=create(client)
    assert patch(client,id,0,b"record").status_code==204
    with store.connect() as conn:
        conn.execute("UPDATE upload_sessions SET updated=? WHERE id=?",(time.time()-EXPIRY_SECONDS-1,id));conn.commit()
    assert client.head(f"/api/uploads/{id}").status_code==410
    assert not store.part(id).exists()


def test_missing_committed_file_rejected_and_auto_language(client):
    id,body=create(client,language="auto")
    assert patch(client,id,0,b"record").status_code==204
    UploadStore(server.UPLOADS).part(id).unlink()
    assert client.head(f"/api/uploads/{id}").status_code==409
    assert client.delete(f"/api/uploads/{id}").status_code==204


def test_raw_chunk_limit_before_body_parsing(client):
    id,_=create(client)
    response=client.patch(f"/api/uploads/{id}",headers={"Upload-Offset":"0","Content-Length":str(8*1024*1024+1),"Content-Type":"application/octet-stream"},content=b"")
    assert response.status_code==413


def test_auto_language_and_restart_keep_one_recording(client):
    id,_=create(client,language="auto")
    assert patch(client,id,0,b"recording").status_code==204
    assert client.post(f"/api/uploads/{id}/complete").status_code==200
    assert server.JOBS[id]["_lang"] is None
    server.JOBS.clear()
    library.interrupt_pending()
    assert library.get(id)["status"]=="error"
    assert client.post(f"/api/uploads/{id}/complete").json()["job_id"]==id
    assert library.count()==1 and server._pending.qsize()==1
    assert client.get(f"/api/library/{id}/media").content==b"recording"
