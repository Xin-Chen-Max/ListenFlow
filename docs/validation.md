# Validation

## Inline cues and bounded loading (2026-10-24)

Local backend/smoke/publication checks passed 158 tests and 16 subtests in 21.09 s, with one existing TestClient deprecation warning. The curated export separately passed 147 tests in 11.36 s, using documented FFmpeg settings. Full Chrome acceptance passed actual desktop transcription/playback/edit/export/restart/deletion/retry plus inline cues, phone strikethrough, sentence/Unicode placement, lazy evidence/error/retry/cache, stale-response protection, selection/node preservation and mobile layout. No browser error or external request was recorded.

A 1,200-segment synthetic Library fixture measured 1,038 ms to first cues, 408 ms to first details, 133 ms for cached details with no new request. Initial summary/detail bodies were 272,835 / 37,663 bytes; no full-transcript analysis was requested. This is one warm-server run including browser-test overhead. See [speech opportunities](speech-opportunities.md) for exact CPU/payload measurements and limitations. No runtime dependency changed. New remote CI, clean Windows and container checks are unrun; no acoustic verification is implemented.


## Dictionary-backed speech opportunities (2026-10-24)

The full local backend/smoke/publication suite passed 143 tests and 16 subtests in 21.00 s. From the curated source directory, 132 tests passed in 11.37 s with the documented FFmpeg settings. Both runs reported one existing Starlette TestClient/httpx deprecation warning. JavaScript syntax and full Chrome acceptance passed, including actual local transcription, playback/edit/export/restart/deletion/retry and the new candidate/evidence/coverage/error/stale-response/cross-segment/missing-audio behavior.

Six text-rule families have positive and negative tests. Dictionary/license hashes, alternative pronunciations, stress assumptions, original token offsets, conservative timing boundaries and the prohibition on acoustic claims are checked. Extra text/timing fixtures test UI behavior; their timestamps are not accuracy evidence. See [speech opportunities](speech-opportunities.md) for exact CPU long-transcript measurements and the large-response limitation.

No runtime dependency version changed. New remote CI, clean Windows installation and container builds are unrun for this increment. No acoustic verifier, G2P model or aligner adapter is implemented. Older installation/GPU results below describe their recorded release environment.

The desktop workflow was exercised on Windows with an NVIDIA RTX 5090. These results establish the tested workflows and fixtures; they do not establish general accent accuracy or learning outcomes.

## Regression checks

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q
node --check static/app.js
```

Tests cover retained media, saved corrections, restart interruption state, retry, deletion, clips, explicit pattern uncertainty, private-access rejection, upload offsets, lost acknowledgements, interrupted writes, duplicate completion, cancellation, expiry and limits. Storage tests stub ASR and use temporary databases/media. Existing upstream unit tests also cover the transcript library, export helpers, optional insights and diarization logic.

On 2026-10-24, the selected source directory passed 80 tests in 8.14 seconds, with one inherited TestClient/AnyIO deprecation warning. JavaScript syntax checks passed. The check reused the existing Python environment and FFmpeg installation; it was not a fresh dependency installation. Optional real-pipeline and export checks are also available in test_smoke.py.

The CI workflow runs Linux regression checks and a fresh Windows installation through setup.bat, followed by launcher checks, CPU transcription and an installed-environment dependency audit. It does not validate an NVIDIA GPU, browser playback, or a physical phone. Both jobs passed in [the published workflow run](https://github.com/Xin-Chen-Max/ListenFlow/actions/runs/40129750875).

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

Dependency remediation and the full local CUDA/browser workflow passed on 2026-10-24; the 87-test backend/smoke suite passed in 25.05 seconds, and three additional launcher tests passed. Clean Windows installation passed as recorded below. Real private-proxy identity requests, Android APK/device delivery, and a 120-minute locked-screen recording remain incomplete. No phone or deployment acceptance is inferred from a responsive browser screenshot. See [security notes](../SECURITY.md) for the current dependency findings.


## Clean Windows installation

[Workflow run 40129750875](https://github.com/Xin-Chen-Max/ListenFlow/actions/runs/40129750875), source commit `c7f3b7dc232e03ccfc6696ce1a493337e8b51033`, completed successfully on 2026-10-24. The fresh GitHub-hosted VM used Windows Server 2025 (windows-2025-vs2026 image 20261021.278.1), CPython 3.12.10 and FFmpeg 9.0.2. No development-machine environment, model cache, recordings or credentials were copied to it.

The Windows job installed through `setup.bat cpu --no-pause`, checked package/prerequisite compatibility, and passed 83 selected regression/launcher tests in 12.31 seconds. The real CPU/int8 tiny-model smoke check passed all three export/pipeline checks. It used the documented four-second tone fallback because that FFmpeg build lacked flite; this verifies pipeline execution and exports, not speech-recognition accuracy. The separate local CUDA speech tests provide speech/timestamp evidence.

The installed Windows environment's dependency audit returned no known vulnerabilities. The Linux regression and JavaScript checks passed in the same workflow. Hosted Windows includes its standard system/build runtimes; a separate manual installation on a blank consumer Windows 11 PC was not performed.
