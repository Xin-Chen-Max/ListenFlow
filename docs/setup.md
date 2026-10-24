# Windows Setup

## Install prerequisites

1. Install Python 3.12 from [python.org](https://www.python.org/downloads/windows/), including the Python launcher. Confirm `py -3.12 --version` works in a new terminal.
2. Install FFmpeg with FFprobe. [FFmpeg's download page](https://ffmpeg.org/download.html) links to Windows builds. Add the extracted bin directory to PATH, then open a new terminal and check `ffmpeg -version` and `ffprobe -version`.
3. Install the [Microsoft Visual C++ x64 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist). CTranslate2 uses this native runtime on Windows. It may already be present.
4. Download this repository as a ZIP and extract it into a writable folder, or clone it with Git. Keep the source folder for future runs.

If using a Python installation without the launcher, set LISTENFLOW_PYTHON to the full path of its python.exe before setup. FFmpeg/FFprobe paths can also be supplied through FFMPEG_PATH and FFPROBE_PATH; each accepts a program path or its containing directory.

## First setup

Double-click setup.bat for CPU setup. For an NVIDIA machine, open a terminal in the project folder and use:

```powershell
.\setup.bat gpu
```

The NVIDIA option installs the tested CUDA runtime wheels into .venv. Install an appropriate NVIDIA driver separately; setup does not change your driver. A working CUDA inference check is required for the GPU indicator. The app reports CPU fallback when GPU execution is unavailable.

Setup creates a Python environment, installs pinned dependencies, checks package compatibility, and verifies FFmpeg/FFprobe. Re-running it reuses .venv. For automated checks, use `setup.bat cpu --no-pause` or `setup.bat gpu --no-pause`.

Manual CPU setup:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2,<27"
.venv\Scripts\python.exe -m pip install -r requirements-cpu.txt
.venv\Scripts\python.exe scripts/check_setup.py
```

Use requirements.txt in place of requirements-cpu.txt for the NVIDIA runtime wheels.

## Start and stop

Double-click run.bat. The browser opens after the local server is ready. Keep the window open while using ListenFlow. Press Ctrl+C in that window to stop it.

For a terminal session without opening a browser:

```powershell
.\run.bat --no-browser
```

The default address is [127.0.0.1:8765](http://127.0.0.1:8765). Use one process per library. If the port is occupied, close the existing server before starting another. The desktop launcher refuses a configured private mode instead of bypassing it.

## First transcription

Choose a short English audio/video file, select tiny for an initial test, and start transcription. The default model remains small. The first use of each model downloads its files; later runs use the local cache. Keep the computer awake during transcription. No cloud transcription fallback is enabled.

After completion, play the audio, click a word to seek, try a sentence loop, and save a difficult clip. Reopen the recording from Library after restarting the server. Corrections are saved with **Save edits**, and TXT/SRT exports use the saved text.

## Local files

uploads stores retained source recordings, output stores exports, and library stores SQLite metadata and practice clips. Deleting a Library entry removes its related files. Deleting .venv is separate from deleting recordings; preserve your local data when moving or upgrading the project.

Models and tools are not included in Git. Use LISTENFLOW_DATA_DIR to choose a different data folder, or LIBRARY_DB to override the database location. Back up recordings and library metadata together if you need to preserve them.

## Troubleshooting

| Message | What to check |
|---|---|
| Python launcher or 3.12 not found | Install Python 3.12 with its launcher, or set LISTENFLOW_PYTHON |
| FFmpeg not found | Add its bin directory to PATH and reopen the terminal, or set FFMPEG_PATH/FFPROBE_PATH |
| Model download fails | Check internet access for the first download and retry; recordings remain local |
| Native DLL import fails | Install the Microsoft Visual C++ x64 runtime, then rerun setup |
| CPU fallback | Verify the NVIDIA driver and GPU setup; CPU execution does not validate CUDA |
| Port already in use | Stop the existing process; do not start a second server over the same library |
| Recording interrupted after restart | Retry it explicitly from Library; its retained audio is reused |
| Deletion blocked by a file lock | Stop playback and close programs holding the file, then retry |

The cache symlink warning on Windows may use additional disk space; it does not by itself mean a transcription failed. Do not run as administrator solely to suppress it.
