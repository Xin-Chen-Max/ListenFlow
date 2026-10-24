r"""Reproducible real-ASR checks. Writes only ignored validation artifacts.

Run from the repository: .venv\Scripts\python.exe scripts/validate_local.py
Synthetic Windows voices check functionality, not human-accent accuracy.
"""

from __future__ import annotations

import hashlib
import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import transcribe_core as core

TEXT = (
    "Welcome to ListenFlow. Today we are practicing English listening. "
    "When you hear a difficult sentence, take your time and listen again. "
    "You can slow down the recording and follow the words on the screen. "
    "Save a useful phrase so you can practice it tomorrow. "
    "Good listening develops through regular practice and careful attention. "
    "Try to understand the meaning before you worry about every single word. "
    "Now play the recording again and notice how the words connect."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accented", type=Path, help="Optional local human-accented validation recording")
    args = parser.parse_args()
    folder = BASE / "validation-artifacts"
    folder.mkdir(exist_ok=True)
    device, compute, note = core.resolve_device()
    report = {
        "python": platform.python_version(), "device": device,
        "compute_type": compute, "device_note": note, "model": "tiny",
        "accented_sample_tested": bool(args.accented),
        "versions": {p: importlib.metadata.version(p) for p in (
            "faster-whisper", "ctranslate2", "nvidia-cublas-cu12", "nvidia-cudnn-cu12")},
        "fixtures": [], "limitations": [
            "Synthetic Windows voices are repeatable functional fixtures, not human-accent accuracy evidence.",
            "Tiny verifies execution; it does not establish final transcription quality.",
        ],
    }
    cases = [("clear-speech", "Microsoft Zira Desktop"), ("alternate-voice", "Microsoft David Desktop"), ("silence", None)]
    if args.accented:
        cases.append(("accented-speech", "external"))
    for name, voice in cases:
        clip = folder / (name + ".wav")
        if voice == "external":
            clip = args.accented.resolve()
            source_args = None
        elif voice:
            raw = folder / (name + "-raw.wav")
            # Values are fixed constants; SAPI uses no network or microphone.
            ps = ("Add-Type -AssemblyName System.Speech; "
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  f"$s.SelectVoice('{voice}'); $s.Rate=-1; "
                  f"$s.SetOutputToWaveFile('{raw}'); "
                  f"$s.Speak('{TEXT}'); $s.Dispose()")
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], check=True)
            source_args = ["-i", str(raw)]
        else:
            source_args = ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono"]
        if source_args:
            subprocess.run([core.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                            *source_args, "-t", "40", "-af", "apad",
                            "-ac", "1", "-ar", "16000", str(clip)], check=True)
        started = time.perf_counter()
        events = list(core.transcribe(str(clip), model_name="tiny", language="en"))
        elapsed = time.perf_counter() - started
        errors = [e for e in events if e["type"] == "error"]
        done = next((e for e in events if e["type"] == "done"), None)
        words = [w for s in (done or {}).get("segments", []) for w in s.get("words", [])]
        passed = bool(done and not errors and (not voice or words))
        if words:
            passed = passed and all(0 <= w["start"] <= w["end"] <= done["duration"] + .5 for w in words)
        if voice is None:
            passed = passed and not (done or {}).get("segments", [])
        item = {"name": name, "voice": voice, "sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
                "duration_seconds": (done or {}).get("duration"), "processing_seconds": round(elapsed, 3),
                "word_count": len(words), "passed": passed, "errors": errors,
                "transcript": " ".join(s["text"] for s in (done or {}).get("segments", []))}
        report["fixtures"].append(item)
        print(json.dumps({k: v for k, v in item.items() if k != "transcript"}), flush=True)
    report["passed"] = device == "cuda" and all(f["passed"] for f in report["fixtures"])
    (folder / "gpu-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"GPU validation: {'PASS' if report['passed'] else 'FAIL'} ({note})")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
