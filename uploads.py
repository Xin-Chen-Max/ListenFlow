"""Durable sequential uploads. Committed SQLite offsets are authoritative."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
import re
import threading
import time
import uuid
from fastapi import HTTPException
import library
import access

_LOCK = threading.RLock()
EXPIRY_SECONDS = 7 * 24 * 3600


class UploadStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.incoming = self.root / ".incoming"
        self.incoming.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = library._connect()
        conn.execute("""CREATE TABLE IF NOT EXISTS upload_sessions (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, client_id TEXT NOT NULL,
            name TEXT NOT NULL, length INTEGER NOT NULL, offset INTEGER NOT NULL DEFAULT 0,
            model TEXT NOT NULL, language TEXT NOT NULL, diarize INTEGER NOT NULL,
            updated REAL NOT NULL, status TEXT NOT NULL DEFAULT 'uploading', job_id TEXT,
            UNIQUE(owner, client_id))""")
        conn.commit()
        try:
            yield conn
        finally:
            conn.close()

    def part(self, id):
        if not re.fullmatch(r"[a-f0-9]{32}", id):
            raise HTTPException(404, "Unknown upload.")
        return self.incoming / (id + ".part")

    def destination(self, row):
        suffix = Path(row["name"]).suffix.lower()
        suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ".media"
        return self.root / row["id"] / ("source" + suffix)

    def row(self, conn, id, owner):
        self.part(id)
        row = conn.execute("SELECT * FROM upload_sessions WHERE id=? AND owner=?", (id, owner)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown upload.")
        if row["status"] in ("cancelled", "expired"):
            raise HTTPException(410, "Upload is no longer available. Start a new upload.")
        return row

    def expire(self, conn):
        for row in conn.execute("SELECT * FROM upload_sessions WHERE status='uploading' AND updated<?",
                                (time.time() - EXPIRY_SECONDS,)).fetchall():
            self.part(row["id"]).unlink(missing_ok=True)
            # A crash may have moved the file before the final database transaction.
            dest = self.destination(row)
            if dest.exists() and not conn.execute("SELECT 1 FROM transcripts WHERE id=?", (row["id"],)).fetchone():
                dest.unlink()
                dest.parent.rmdir()
            conn.execute("UPDATE upload_sessions SET status='expired' WHERE id=?", (row["id"],))
        conn.commit()

    def reconcile(self, conn, row):
        if row["status"] == "completed":
            return row
        part = self.part(row["id"])
        if not part.exists():
            dest = self.destination(row)
            if row["offset"] == row["length"] and dest.is_file() and dest.stat().st_size == row["length"]:
                return row  # Recover the move-before-database-commit window.
            if row["offset"]:
                raise HTTPException(409, "Partial upload is missing; cancel it and upload the retained phone copy again.")
            part.touch()
        size = part.stat().st_size
        if size < row["offset"]:
            raise HTTPException(409, "Committed upload data is missing; cancel and restart this upload.")
        if size > row["offset"]:
            with part.open("r+b") as f:
                f.truncate(row["offset"])
                f.flush()
                os.fsync(f.fileno())
        return row

    @staticmethod
    def public(row):
        return {k: row[k] for k in ("id", "length", "offset", "status", "job_id")}

    def create(self, owner, client_id, name, length, model, language, diarize):
        try:
            client_id = str(uuid.UUID(client_id))
        except ValueError:
            raise HTTPException(400, "client_id must be a UUID.")
        name = Path(name.replace("\\", "/")).name
        if not name or len(name) > 255:
            raise HTTPException(400, "A filename of at most 255 characters is required.")
        if not 0 < length <= access.get_max_upload_bytes():
            raise HTTPException(413, "File size exceeds the upload limit or is empty.")
        with _LOCK, self.connect() as conn:
            self.expire(conn)
            row = conn.execute("SELECT * FROM upload_sessions WHERE owner=? AND client_id=?", (owner, client_id)).fetchone()
            if row:
                if row["status"] == "completed" and not conn.execute("SELECT 1 FROM transcripts WHERE id=?", (row["id"],)).fetchone():
                    raise HTTPException(410, "The saved recording was deleted. Start a new upload explicitly.")
                if (row["name"],row["length"],row["model"],row["language"],bool(row["diarize"])) != (name,length,model,language,diarize):
                    raise HTTPException(409, "Upload UUID already refers to a different file or settings.")
                row = self.row(conn, row["id"], owner)
            else:
                id = uuid.uuid4().hex
                conn.execute("INSERT INTO upload_sessions (id,owner,client_id,name,length,model,language,diarize,updated) VALUES (?,?,?,?,?,?,?,?,?)",
                             (id,owner,client_id,name,length,model,language,int(diarize),time.time()))
                conn.commit()
                row = self.row(conn,id,owner)
            self.reconcile(conn,row)
            return self.public(row)

    def status(self, id, owner):
        with _LOCK, self.connect() as conn:
            self.expire(conn)
            row = self.reconcile(conn,self.row(conn,id,owner))
            conn.execute("UPDATE upload_sessions SET updated=? WHERE id=?",(time.time(),id))
            conn.commit()
            return self.public(row)

    def patch(self, id, owner, offset, data):
        if not data or len(data) > access.CHUNK_BYTES:
            raise HTTPException(413, "Chunks must contain 1 to 8 MiB of data.")
        with _LOCK, self.connect() as conn:
            self.expire(conn)
            row = self.reconcile(conn,self.row(conn,id,owner))
            if row["status"] != "uploading":
                raise HTTPException(409,"Upload is already complete.")
            if offset != row["offset"]:
                raise HTTPException(409,"Refresh the authoritative upload offset.", headers={"Upload-Offset":str(row["offset"])})
            if offset + len(data) > row["length"]:
                raise HTTPException(413,"Chunk exceeds declared file length.")
            with self.part(id).open("r+b") as f:
                f.seek(offset)
                try:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                    conn.execute("UPDATE upload_sessions SET offset=?,updated=? WHERE id=?",(offset+len(data),time.time(),id))
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    f.truncate(offset)
                    f.flush()
                    os.fsync(f.fileno())
                    raise
            return offset+len(data)

    def complete(self, id, owner):
        with _LOCK, self.connect() as conn:
            self.expire(conn)
            row = self.reconcile(conn,self.row(conn,id,owner))
            if row["status"] == "completed":
                return row["job_id"]
            if row["offset"] != row["length"]:
                raise HTTPException(409,"Upload is incomplete.")
            destination = self.destination(row)
            destination.parent.mkdir(exist_ok=True)
            part = self.part(id)
            if part.exists():
                os.replace(part,destination)
            # Deterministic recording ID plus one transaction makes completion idempotent.
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""INSERT OR IGNORE INTO transcripts
                (id,name,created_at,duration,language,model,source,text,segments,media_path,status,error,diarize)
                VALUES (?,?,?,0,?,?, 'mobile','', '[]',?,'queued','',?)""",
                (id,row["name"],time.time(),row["language"],row["model"],destination.relative_to(self.root).as_posix(),row["diarize"]))
            conn.execute("UPDATE upload_sessions SET status='completed',job_id=?,updated=? WHERE id=?",(id,time.time(),id))
            conn.commit()
            return id

    def cancel(self, id, owner):
        with _LOCK, self.connect() as conn:
            row = self.row(conn,id,owner)
            if row["status"] == "completed":
                raise HTTPException(409,"Delete the saved recording through Library instead.")
            self.part(id).unlink(missing_ok=True)
            destination=self.destination(row)
            if destination.exists():
                destination.unlink()
                destination.parent.rmdir()
            conn.execute("UPDATE upload_sessions SET status='cancelled',updated=? WHERE id=?",(time.time(),id))
            conn.commit()
