"""
Transcript library: a small local store of every finished transcript, with
global search across all of them. Pure stdlib (sqlite3), fully local.

Both backends record here when a job finishes:
  - the single-process app writes to a library.db next to its output/, and
  - the queue worker writes to library.db on the shared volume (SHARED_DIR),
    which the API reads. SQLite's file locking handles the two processes.

Location resolution (first that applies):
  LIBRARY_DB   an explicit path to the database file
  SHARED_DIR   -> $SHARED_DIR/library.db   (the queue deployment)
  otherwise    -> <repo_root>/library/library.db
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

_REPO = Path(__file__).resolve().parent


def db_path() -> Path:
    explicit = os.environ.get("LIBRARY_DB")
    if explicit:
        return Path(explicit)
    shared = os.environ.get("SHARED_DIR")
    if shared:
        return Path(shared) / "library.db"
    data = os.environ.get("LISTENFLOW_DATA_DIR")
    if data:
        return Path(data) / "library" / "library.db"
    return _REPO / "library" / "library.db"


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            created_at  REAL NOT NULL,
            duration    REAL DEFAULT 0,
            language    TEXT DEFAULT '',
            model       TEXT DEFAULT '',
            source      TEXT DEFAULT '',
            text        TEXT NOT NULL,
            segments    TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_transcripts_created ON transcripts(created_at DESC)")
    columns = {r[1] for r in conn.execute("PRAGMA table_info(transcripts)")}
    for name, declaration in {
        "media_path": "TEXT DEFAULT ''", "status": "TEXT DEFAULT 'done'",
        "error": "TEXT DEFAULT ''", "diarize": "INTEGER DEFAULT 0",
    }.items():
        if name not in columns:
            try:
                conn.execute(f"ALTER TABLE transcripts ADD COLUMN {name} {declaration}")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise
    conn.execute("""CREATE TABLE IF NOT EXISTS clips (
        id TEXT PRIMARY KEY,
        transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
        segment_index INTEGER NOT NULL,
        start REAL NOT NULL, end REAL NOT NULL, text TEXT NOT NULL,
        UNIQUE(transcript_id, segment_index)
    )""")
    conn.commit()
    return conn


def add(
    id: str,
    name: str,
    segments: list,
    duration: float = 0.0,
    language: str = "",
    model: str = "",
    source: str = "",
    created_at: float | None = None,
    media_path: str = "",
    status: str = "done",
    error: str = "",
    diarize: bool = False,
) -> None:
    """Insert or replace a transcript. Safe to call more than once per job."""
    segs = []
    for s in (segments or []):
        entry = {
            "start": float(s.get("start", 0) or 0),
            "end": float(s.get("end", 0) or 0),
            "text": (s.get("text") or "").strip(),
        }
        if s.get("speaker") is not None:
            entry["speaker"] = int(s["speaker"])
        words = s.get("words")
        if words:
            entry["words"] = [
                {"start": float(w.get("start", 0) or 0), "end": float(w.get("end", 0) or 0), "word": w.get("word", "")}
                for w in words
            ]
        segs.append(entry)
    text = "\n".join(s["text"] for s in segs if s["text"])
    if created_at is None:
        created_at = time.time()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO transcripts "
            "(id, name, created_at, duration, language, model, source, text, segments, media_path, status, error, diarize) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id, name or "transcript", created_at, float(duration or 0), language or "",
             model or "", source or "", text, json.dumps(segs), media_path, status, error, int(diarize)),
        )
        conn.commit()
    finally:
        conn.close()


def _snippet(text: str, query: str, radius: int = 70) -> str:
    """A short excerpt of text. If query is given, center it on the first match."""
    text = text.replace("\n", " ").strip()
    if not query:
        return text[: radius * 2] + ("..." if len(text) > radius * 2 else "")
    low = text.lower()
    idx = low.find(query.lower())
    if idx == -1:
        return text[: radius * 2] + ("..." if len(text) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


def list_entries(query: str = "", limit: int = 300, offset: int = 0) -> list[dict]:
    """Newest-first list of transcripts. With a query, only those whose name or
    body contains it, each with a snippet centered on the match."""
    query = (query or "").strip()
    conn = _connect()
    try:
        if query:
            like = f"%{query}%"
            rows = conn.execute(
                "SELECT * FROM transcripts WHERE name LIKE ? OR text LIKE ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (like, like, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transcripts ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    finally:
        conn.close()

    out = []
    for row in rows:
        try:
            seg_count = len(json.loads(row["segments"]))
        except (ValueError, TypeError):
            seg_count = 0
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "duration": row["duration"],
                "language": row["language"],
                "model": row["model"],
                "segment_count": seg_count,
                "snippet": _snippet(row["text"] or "", query),
                "status": row["status"],
                "error": row["error"],
            }
        )
    return out


def get(id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM transcripts WHERE id = ?", (id,)).fetchone()
        clips = [dict(r) for r in conn.execute(
            "SELECT id, segment_index, start, end, text FROM clips WHERE transcript_id=? ORDER BY start", (id,))]
    finally:
        conn.close()
    if not row:
        return None
    try:
        segments = json.loads(row["segments"])
    except (ValueError, TypeError):
        segments = []
    return {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "duration": row["duration"],
        "language": row["language"],
        "model": row["model"],
        "source": row["source"],
        "segments": segments,
        "media_path": row["media_path"],
        "status": row["status"],
        "error": row["error"],
        "diarize": bool(row["diarize"]),
        "clips": clips,
    }


def delete(id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM transcripts WHERE id = ?", (id,))
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='upload_sessions'").fetchone():
            # Retain only the deduplication tombstone, not the deleted recording's metadata.
            conn.execute("UPDATE upload_sessions SET name='',length=0,offset=0,model='',language='',diarize=0 WHERE job_id=?", (id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count() -> int:
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    finally:
        conn.close()


def set_status(id: str, status: str, error: str = "") -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE transcripts SET status=?, error=? WHERE id=?", (status, error, id))
        conn.commit()
    finally:
        conn.close()


def interrupt_pending() -> None:
    """A restarted process cannot resume its old GPU threads. Offer explicit retry."""
    conn = _connect()
    try:
        conn.execute("UPDATE transcripts SET status='error', error=? WHERE status IN ('queued', 'running')",
                     ("Transcription was interrupted by a restart. Retry this recording.",))
        conn.commit()
    finally:
        conn.close()


def complete(id: str, segments: list[dict], duration: float, language: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE transcripts SET segments=?, text=?, duration=?, language=?, status='done', error='' WHERE id=?",
                     (json.dumps(segments), "\n".join(s["text"] for s in segments), duration, language, id))
        conn.commit()
    finally:
        conn.close()


def update_texts(id: str, texts: list[str]) -> bool:
    """Keep segment timing; edited text no longer has trustworthy word alignment."""
    conn = _connect()
    try:
        row = conn.execute("SELECT segments FROM transcripts WHERE id=?", (id,)).fetchone()
        if row is None:
            return False
        segments = json.loads(row["segments"])
        if len(texts) != len(segments):
            raise ValueError("The number of segments changed. Reopen the recording before saving.")
        for index, (seg, text) in enumerate(zip(segments, texts)):
            text = text.strip()
            if text != seg["text"]:
                seg["text"] = text
                seg["words"] = []
                conn.execute("UPDATE clips SET text=? WHERE transcript_id=? AND segment_index=?", (text, id, index))
        conn.execute("UPDATE transcripts SET segments=?, text=? WHERE id=?",
                     (json.dumps(segments), "\n".join(s["text"] for s in segments), id))
        conn.commit()
        return True
    finally:
        conn.close()


def add_clip(id: str, segment_index: int) -> dict:
    conn = _connect()
    try:
        row = conn.execute("SELECT segments FROM transcripts WHERE id=?", (id,)).fetchone()
        if row is None:
            raise ValueError("Recording not found.")
        segments = json.loads(row["segments"])
        if segment_index < 0 or segment_index >= len(segments):
            raise ValueError("Segment not found.")
        seg = segments[segment_index]
        if seg["end"] <= seg["start"]:
            raise ValueError("This segment has no playable duration.")
        conn.execute("INSERT OR IGNORE INTO clips (id, transcript_id, segment_index, start, end, text) VALUES (?, ?, ?, ?, ?, ?)",
                     (uuid.uuid4().hex, id, segment_index, seg["start"], seg["end"], seg["text"]))
        conn.commit()
        return dict(conn.execute("SELECT id, segment_index, start, end, text FROM clips WHERE transcript_id=? AND segment_index=?",
                                 (id, segment_index)).fetchone())
    finally:
        conn.close()


def delete_clip(id: str, clip_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM clips WHERE transcript_id=? AND id=?", (id, clip_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
