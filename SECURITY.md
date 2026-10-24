# Security Notes

ListenFlow is a personal desktop application. Bind it to `127.0.0.1`; do not expose the listener through a router, public tunnel, or hosted endpoint. One process owns the library. Private-mode middleware exists, but real proxy/device acceptance is incomplete.

## Data

Audio, transcripts and clips remain in local storage until deleted. Whisper models download from their upstream source on first use. The default workflow does not upload recordings to a cloud transcription service. Optional Ollama features use the configured endpoint; leave them unconfigured if they are not needed.

Runtime directories, credentials, databases, recordings, model caches and signing keys are excluded from the source selection. Review what a recording contains before sharing a screenshot, export or bug report.

## Dependency audit

Reviewed on 2026-10-24 with pip-audit 2.10.1. The new desktop environment's 61 installed runtime/development packages returned zero known findings, with no ignored advisories. The working desktop environment also passed its audit and pip check. The desktop browser-test package audit returned zero vulnerabilities.

The verified set includes FastAPI 0.136.3, Starlette 1.9.0, python-multipart 0.0.32, pytest 9.0.3 and pip 26.2.2. Updates replaced the earlier affected parsing and development-tool versions. ASR model and CUDA runtime versions remain unchanged.

This is a time-specific package advisory check, not proof that every application path or native component is secure. Recheck advisories when installing or updating dependencies. No public server deployment is supported.

Do not post credentials, private recordings or an exploit against a running personal instance in a public issue. A dedicated private vulnerability-reporting channel has not yet been configured.
