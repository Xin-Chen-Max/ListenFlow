"""Measure dictionary/text analysis on a synthetic long transcript, not accuracy."""

import argparse
import gc
import json
import os
from pathlib import Path
import platform
import sys
import time

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from pronunciation.analysis import analyze
from pronunciation.context import TOKEN


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=int, default=1200)
    parser.add_argument("--bounded", action="store_true", help="Compare full responses with visible-page summaries and lazy details.")
    args = parser.parse_args()
    if args.segments <= 0:
        parser.error("--segments must be positive")
    text = "Need it. Turn off. See it. Did you want to leave? We kept moving. It is better for a moment."
    tokens = list(TOKEN.finditer(text))
    step = .24
    segments = []
    for si in range(args.segments):
        start = si * len(tokens) * step
        words = [{"word": m.group(), "start": start + ti*step, "end": start + (ti+1)*step}
                 for ti, m in enumerate(tokens)]
        segments.append({"text": text, "start": start, "end": words[-1]["end"], "words": words})
    report = {"python": platform.python_version(), "os": platform.platform(),
              "cpu_identifier": platform.processor(), "logical_cpus": os.cpu_count(),
              "segments": len(segments), "tokens": len(tokens)*len(segments),
              "fixture_duration_seconds": segments[-1]["end"], "runs": [],
              "limits": "Synthetic repeated text; CPU text analysis only, no acoustic accuracy or GPU benchmark. First run includes dictionary loading; no statistical latency guarantee."}
    cases = [("legacy_full", None, "full")] * 3
    if args.bounded:
        cases = [("legacy_full_cold", None, "full"), ("legacy_full_warm", None, "full"),
                 ("visible_summary", 24, "summary"), ("sentence_details", 1, "full")]
    for run, (mode, limit, view) in enumerate(cases):
        gc.collect()
        began = time.perf_counter()
        data = analyze(segments, segment_limit=limit, view=view)
        elapsed = time.perf_counter() - began
        began = time.perf_counter()
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        serialization = time.perf_counter() - began
        report["runs"].append({"mode": mode, "segment_limit": limit, "cold_dictionary": run == 0, "analysis_seconds": round(elapsed, 4),
                               "serialization_seconds": round(serialization, 4),
                               "patterns": len(data["patterns"]), "json_bytes": len(payload)})
        report["engine_version"], report["dictionary_version"] = data["engine_version"], data["dictionary_version"]
        del data, payload
    folder = BASE / "validation-artifacts"
    folder.mkdir(exist_ok=True)
    name = "speech-inline-performance.json" if args.bounded else "speech-performance.json"
    (folder / name).write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
