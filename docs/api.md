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
- GET /api/library/{id}: existing transcript metadata and segments, plus status, error, diarize, clips, nullable media_url and transcript_fingerprint. Internal media paths are not returned.
- GET /api/library/{id}/media: local retained source, supporting range requests. Legacy/missing audio returns 404.
- PATCH /api/library/{id}: JSON `{ "texts": ["First corrected segment", "Second segment"] }`. Requires a completed recording and unchanged segment count. Saves text, keeps segment boundaries, clears word timings only on edited segments, updates saved clip labels, and refreshes exports.
- DELETE /api/library/{id}: removes the source folder, export folder, database entry, and clips. Active jobs return 409. Files still in use after a bounded Windows retry return an actionable 409. Missing IDs return 404.

Uploads use generated storage names. Media and deletion paths must resolve inside the recording's own directory. Original display filenames never choose arbitrary storage paths.

## Learning

- POST /api/library/{id}/clips: JSON `{ "segment_index": 0 }`. Saves that timestamped segment; repeated saves of the same segment return the same clip. Requires a completed recording.
- DELETE /api/library/{id}/clips/{clip_id}: removes only the clip belonging to that recording, preserving the recording itself.
- GET /api/library/{id}/patterns: returns a versioned derived analysis envelope with the existing patterns array. Label remains Possible pattern; evidence remains text-rule. Timing is words when the saved words reliably match, otherwise segment. Dictionary loading, SQLite reads, analysis and response encoding run off the event loop.

Envelope fields: schema_version (1.0), engine_version, dictionary_version, transcript_fingerprint, coverage (token_count, dictionary_token_count and diagnostics), capabilities, settings (max_boundary_gap_seconds, default 0.25), patterns. No new database state or analysis cache is written.

Optional query parameters preserve the default full response:

| Parameter | Behavior |
|---|---|
| segment_start | Nonnegative first segment, default 0 |
| segment_limit | 1–48 segments; omitted retains the full remaining transcript |
| view | full (default) or summary |
| fingerprint | Expected saved transcript fingerprint; mismatch returns 409 before analysis |

Both views include range (segment_start, segment_end exclusive, total_segments) and view metadata. Ranged analysis includes two neighboring segments on either side for context, then filters to opportunities touching the requested segments. IDs, global token/character references and replay intervals agree with full analysis. Coverage counts and diagnostics describe the requested range only. Invalid limits/start/view return 422.

summary retains identity, rule/category/status, label/evidence, phrase/tokens/segment references, replay intervals/timing, null confidence and notation. It omits detailed pronunciation alternatives, explanations, assumptions and evidence lists. full retains those fields. Notation contains a short label, typed text/link/omission parts, illustrative=true and an explicit example-only note. It does not select a variant as recorded or claim a sound was omitted. Omission marks apply to the eligible phone, not the original transcript spelling.

The browser requests 24-segment summaries near the viewport and one-segment full details on click. It caches them per recording/fingerprint, aborts superseded requests after edits and never requests the unbounded endpoint. Applying summaries updates cues and underline classes without replacing word nodes. No server-side analysis cache, database migration or dependency was added.

Each pattern retains segment_index, phrase, category, label, evidence, explanation, accent_note, start, end and timing. Additive fields:

| Field | Meaning |
|---|---|
| id, rule_id, rule_version | Stable analysis result and versioned rule identity |
| status | candidate or uncertain in this text-only stage |
| tokens, target_token_ids | Original token identity, offsets, spelling/normalization and affected targets |
| segment_indices | All affected segments; cross-segment cards appear beside either segment |
| timing_provenance | Existing ASR word timestamps or saved segment timestamps; no phone alignment implied |
| source_audio | Existing authenticated relative media URL, or null for missing/legacy audio |
| transcript_fingerprint | SHA-256 of saved text, times, words and speakers |
| pronunciations | All dictionary variants, ARPABET, broad IPA and supporting variant IDs |
| evidence_sources, assumptions | Saved-text/dictionary/rule provenance and contextual limitations |
| confidence, confidence_reason | null and the explicit uncalibrated reason |

Categories use stable IDs linking, reduction, elision, assimilation, consonant_phenomena, prosody; the capability taxonomy supplies display names. Six implemented text rules are listed in [speech opportunities](speech-opportunities.md). Function-word targets mark weak alternatives separately from strong ones. Equivalent rule/span matches are grouped; different overlapping rules remain distinct.

The browser compares item and analysis fingerprints and rejects differing versions. Request generations also discard responses superseded by edits. Missing/stale timing uses segment replay; cross-segment candidates require valid continuous word timing. Coverage diagnoses unknown words, unsupported normalization, stale/missing words and invalid segment times. A successful empty result makes no claim about the presence or absence of connected speech. Failed requests show a retryable error.

observed and not_observed are reserved for a separately validated acoustic stage. They are never emitted by this increment. A forced alignment, dictionary match, or lexical stress mark is not pronunciation verification. Confidence is not inferred from dictionary order, alignment or a rule match.

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
