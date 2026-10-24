# Validation

The desktop workflow was exercised on Windows with an NVIDIA RTX 5090. These results establish the tested workflows and fixtures; they do not establish general accent accuracy or learning outcomes.

## Regression checks

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q
node --check static/app.js
```

Tests cover retained media, saved corrections, restart interruption state, retry, deletion, clips, explicit pattern uncertainty, private-access rejection, upload offsets, lost acknowledgements, interrupted writes, duplicate completion, cancellation, expiry and limits. Storage tests stub ASR and use temporary databases/media. Existing upstream unit tests also cover the transcript library, export helpers, optional insights and diarization logic.

On 2026-10-24, the selected source directory passed 80 tests in 8.14 seconds, with one inherited TestClient/AnyIO deprecation warning. JavaScript syntax checks passed. The check reused the existing Python environment and FFmpeg installation; it was not a fresh dependency installation. Optional real-pipeline and export checks are also available in test_smoke.py.

The CI workflow runs Linux regression checks and a fresh Windows installation through setup.bat, followed by launcher checks, CPU transcription and an installed-environment dependency audit. It does not validate an NVIDIA GPU, browser playback, or a physical phone. CI execution on a newly published repository is still required.

## Browser acceptance

The Playwright check runs a separate server with an isolated library. It performs actual local transcription, verifies playback highlighting, text seek, speed, replay and loops, saves edits/clips, checks exports, stops and restarts the server, reopens the recording, deletes it after playback, and retries a failed job.

On Windows with the Microsoft Zira Desktop and David Desktop voices, generate fixtures first:

```powershell
.venv\Scripts\python.exe scripts/validate_local.py
npm.cmd ci
npm.cmd run test:ui
```

The fixture script requires successful CUDA execution for a passing result. Google Chrome and the tiny model cache are required for the browser check. A browser run after fixture generation was passed on the development machine. Artifacts stay under ignored validation-artifacts; test processes are stopped by the harness.

## Recorded CUDA run

2026-10-24: RTX 5090, driver 617.42, Python 3.12.14, FFmpeg 9.0.2, faster-whisper 1.1.1, CTranslate2 4.8.0. Actual inference: CUDA/float16, tiny model. Runtime wheels: cuBLAS 12.9.2.10, cuDNN 9.23.1.3, NVRTC 12.9.86.

| Sample | Audio duration | Processing time |
|---|---|---|
| Microsoft Zira synthetic English | 40.0 s | 3.390 s |
| Microsoft David synthetic English | 40.0 s | 2.766 s |
| Silence | 40.0 s | 1.056 s |
| AccentCL british_isles sample00 | 30.0 s | 3.154 s |

Checks required successful completion, valid timestamp ranges, words for speech, and no transcript for silence. Synthetic voices test functionality. A single accent-labelled sample is not an accuracy benchmark.

The optional human fixture comes from [AccentCL](https://github.com/PSI-TAMU/AccentCL/blob/a37811a5b772b1056cd90d44666585e35aedd657/samples/british_isles/sample00.wav), pinned at `a37811a5b772b1056cd90d44666585e35aedd657`. SHA-256: `9fc97b16ff2a75c350294fcebe26e9dc55d640f94b8c2dd8f3e832024e278bb5`. It is not redistributed. The source's accent label was not independently verified.

## Remaining checks

Dependency remediation and the full local CUDA/browser workflow passed on 2026-10-24; the 87-test backend/smoke suite passed in 25.05 seconds, and three additional launcher tests passed. A clean Windows runner install is still pending remote execution. Real private-proxy identity requests, Android APK/device delivery, and a 120-minute locked-screen recording remain incomplete. No phone or deployment acceptance is inferred from a responsive browser screenshot. See [security notes](../SECURITY.md) for the current dependency findings.
