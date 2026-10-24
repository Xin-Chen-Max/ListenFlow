"""Check desktop prerequisites without downloading a model or starting inference."""
from pathlib import Path
import importlib.metadata
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        print('Python 3.12 is required for the tested setup.')
        return 1
    try:
        import transcribe_core as core
        for label, program in [('FFmpeg', core.FFMPEG), ('FFprobe', core.FFPROBE)]:
            subprocess.run([program, '-version'], check=True, capture_output=True)
            print(label + ': available')
        for package in ['fastapi', 'starlette', 'python-multipart', 'faster-whisper', 'ctranslate2']:
            print(package + ': ' + importlib.metadata.version(package))
    except Exception as exc:
        print('Setup check failed: ' + str(exc))
        print('Install FFmpeg and FFprobe on PATH; see docs/setup.md.')
        return 1
    print('Desktop prerequisites passed. The application checks CUDA when transcription starts.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
