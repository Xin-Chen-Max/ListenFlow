"""Discover project-local tools and Windows CUDA wheels without system changes."""

from __future__ import annotations

import os
import site
from pathlib import Path

BASE = Path(__file__).resolve().parent
_DLL_HANDLES = []


def configure() -> None:
    os.environ.setdefault("HF_HOME", str(BASE / "model-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    bins = []
    if os.name == "nt":
        for root in site.getsitepackages():
            for folder in sorted((Path(root) / "nvidia").glob("*/bin")):
                if folder.is_dir():
                    bins.append(str(folder))
                    _DLL_HANDLES.append(os.add_dll_directory(str(folder)))
    for folder in sorted((BASE / ".tools").glob("ffmpeg*/bin")):
        if folder.is_dir():
            bins.append(str(folder))
    if bins:
        os.environ["PATH"] = os.pathsep.join(bins + [os.environ.get("PATH", "")])


configure()
