# Upstream and ListenFlow Changes

Foundation: [SFX-TECH/local-transcriber](https://github.com/SFX-TECH/local-transcriber), pinned at `cade4b72c7ff2ebf1ea95aa51618960c24c6673d`.

Original author: Jesse Jolly (SFX Tech Innovation). The upstream MIT license and copyright notice are preserved in LICENSE.

| Area | Upstream foundation | ListenFlow additions |
|---|---|---|
| Transcription | FFmpeg, faster-whisper/CTranslate2, device selection, timestamped segments | RTX 5090 validation and project-local Windows CUDA/tool discovery |
| Playback | Word highlighting and synchronized transcript navigation | Retained audio on reopen, sentence loops, Smart Replay, playback speed controls |
| Library | SQLite transcript library and search | Recording lifecycle, restart interruption reporting, audio retention, explicit deletion and retry |
| Editing/export | Transcript editing and export formats | Persisted corrections and exports from saved text |
| Practice | General transcription interface | Saved difficult clips and text-derived connected-speech candidates |
| Uploads/access | Local file upload | Durable chunk sessions, authoritative offsets, idempotent completion, private-mode middleware and process ownership guard |
| Verification | Existing smoke and unit tests | Persistence/failure/deletion, access/upload contracts, learning rules, browser playback and process-restart checks |

The speech recognition models and underlying transcription engine are existing open-source work. ListenFlow does not claim model training, a new ASR architecture, or measured improvement in recognition accuracy.

The original [CMU US English pronunciation dictionary](pronunciation/data/cmudict/PROVENANCE.md) is bundled at a pinned commit with its own unchanged [license](pronunciation/data/cmudict/LICENSE). ListenFlow supplies the reader, context rules and learner interface; dictionary alternatives are text evidence and do not establish recorded pronunciation. No third-party dictionary wrapper, G2P runtime or forced aligner is included.

This source selection covers the desktop application. The upstream queue/Kubernetes service and the unfinished native mobile companion are outside this version's scope. Optional local Ollama insights and speaker diarization come from the upstream application; they are not required for the listening workflow.
