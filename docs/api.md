# ListenFlow Local API

The supported entrypoint is app:app, one process bound to localhost. These additions extend the inherited API; no cloud provider or public authentication service was added.

## Recording lifecycle

- POST /api/jobs: multipart file, model, language, optional diarize. Returns job_id, name, and size. Records a queued library entry and retains its uploaded media.
- GET /api/jobs/{id}/events: replayable SSE events with numeric IDs, Last-Event-ID reconnect support, and an end event. A restarted process reports interrupted jobs as errors with a retry option.
- POST /api/jobs/{id}/retry: accepts only failed/interrupted jobs with retained media; resets and requeues the existing recording. Returns job_id. Active/completed jobs return 409.
- GET /api/jobs/{id}/download/{fmt}: TXT, SRT, or VTT from persisted current text, including after a restart.

States: queued → running → done/error. On startup, previously queued/running entries become interrupted errors; jobs do not silently restart expensive work.

## Library and editing

- GET /api/library?q=: existing searchable entries plus status and error fields.
- GET /api/library/{id}: existing transcript metadata and segments, plus status, error, diarize, clips, and nullable media_url. Internal media paths are not returned.
- GET /api/library/{id}/media: local retained source, supporting range requests. Legacy/missing audio returns 404.
- PATCH /api/library/{id}: JSON `{ "texts": ["First corrected segment", "Second segment"] }`. Requires a completed recording and unchanged segment count. Saves text, keeps segment boundaries, clears word timings only on edited segments, updates saved clip labels, and refreshes exports.
- DELETE /api/library/{id}: removes the source folder, export folder, database entry, and clips. Active jobs return 409. Files still in use after a bounded Windows retry return an actionable 409. Missing IDs return 404.

Uploads use generated storage names. Media and deletion paths must resolve inside the recording's own directory. Original display filenames never choose arbitrary storage paths.

## Learning

- POST /api/library/{id}/clips: JSON `{ "segment_index": 0 }`. Saves that timestamped segment; repeated saves of the same segment return the same clip. Requires a completed recording.
- DELETE /api/library/{id}/clips/{clip_id}: removes only the clip belonging to that recording, preserving the recording itself.
- GET /api/library/{id}/patterns: returns patterns containing segment_index, phrase, category, label, evidence, explanation, accent_note, start, end, and timing. Label is always Possible pattern; evidence is text-rule. Timing is words when the matched words align, otherwise segment.

Sentence/phrase replay and speed are browser playback controls. Saved clips use transcript segment intervals. Browser playback settings do not change the media file or its timestamps.

## Storage compatibility

SQLite is extended additively with media_path, status, error, and diarize columns and a cascading clips table. Existing transcripts remain readable with done status and no audio link. Store media relative to the uploads root; do not embed machine-specific absolute paths in library rows.

The default library is library/library.db. LIBRARY_DB takes precedence, then the inherited SHARED_DIR location, then LISTENFLOW_DATA_DIR/library/library.db. LISTENFLOW_DATA_DIR also controls uploads and output for the personal app. The inherited queue deployment has not been adapted to the ListenFlow UI contract.

## Resumable native uploads

All routes inherit the access/body-size boundary. Private sessions belong to the verified owner; local-mode sessions use local ownership. A generated UUID never selects an arbitrary disk path.

- POST /api/uploads JSON: client_id (stable UUID), name, length (positive integer bytes), model (default small), language (default en; auto/empty supported), diarize (default false). Returns id, length, offset, status, job_id. Reusing the same owner/client UUID returns the same session; changed file/settings return 409. If its completed computer recording was deleted, create returns 410; an explicit new upload requires a new client UUID. Unsupported files/models return 400; invalid payloads 422; too-large files 413.
- HEAD /api/uploads/{id}: Upload-Offset, Upload-Length, Upload-Status, Upload-Job-Id headers; Cache-Control no-store. Inspect this after a lost acknowledgement or reconnect. An inactive unfinished session expires after seven days (410); create a new client UUID to restart from the retained phone copy.
- PATCH /api/uploads/{id}: Content-Type application/octet-stream and nonnegative Upload-Offset. Send 1 byte through 8 MiB. Success: 204 with next Upload-Offset. Offset disagreement: 409 with current offset; query HEAD instead of blindly resending. Bytes beyond declared length or chunk limit: 413.
- POST /api/uploads/{id}/complete: requires all bytes. Returns job_id and deleted. Repeated completion returns the same recording ID without requeuing completed/failed work. If the saved recording was deleted, deleted is true and completion does not recreate it. Use the existing explicit retry endpoint for ASR errors.
- DELETE /api/uploads/{id}: 204 removes unfinished data; completed sessions require Library deletion. Missing/other-owner sessions: 404; expired/cancelled sessions: 410.

Offsets advance only after file fsync and database commit. HEAD/retry truncates any uncommitted tail. A crash between file placement and final metadata commit is recovered on completion retry. Transcript insertion and upload completion are one SQLite transaction; deterministic recording IDs prevent duplicates. A restarted server marks queued/running work interrupted, preserving explicit ASR retry behavior.

Session metadata is additive in library SQLite; partials use uploads/.incoming. Expiry cleanup is opportunistic on upload operations. Completed-session tombstones remain for idempotency. Library deletion scrubs original filename, size, model and language from that metadata, preserving only the identity/linkage needed to prevent recreation.

## Study deep link

`/?recording=<id>` opens the retained library item directly in the existing synchronized study view. Invalid IDs and unavailable items show an error. The native WebView only allows its configured private HTTPS origin; this route uses the same owner authentication as all other pages and APIs.
