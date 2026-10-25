"""Derived analysis results using saved text, dictionary phones and existing times."""

import hashlib

from . import ENGINE_VERSION, SCHEMA_VERSION
from .context import DEFAULT_GAP_SECONDS, build_context, transcript_fingerprint
from .contracts import AnalysisResult
from .provider import PronunciationProvider, dictionary
from .rules import detect
from .notation import notation
from .taxonomy import capabilities


def analyze(segments: list[dict], source_audio: str | None = None,
            provider: PronunciationProvider | None = None, max_gap: float = DEFAULT_GAP_SECONDS,
            segment_start: int = 0, segment_limit: int | None = None, view: str = "full") -> dict:
    if segment_start < 0 or (segment_limit is not None and not 1 <= segment_limit <= 48):
        raise ValueError("Invalid analysis segment range.")
    if view not in {"full", "summary"}:
        raise ValueError("Invalid analysis representation.")
    provider = provider if provider is not None else dictionary()
    stop = len(segments) if segment_limit is None else min(len(segments), segment_start + segment_limit)
    offset = max(0, segment_start - 2)
    window = segments[offset:min(len(segments), stop + 2)]
    context = build_context(window, provider, max_gap, segment_offset=offset)
    context.fingerprint = transcript_fingerprint(segments)
    results = {}
    for match in detect(context):
        if not any(segment_start <= t.segment + offset < stop for t in match.tokens):
            continue
        first, last = match.tokens[0], match.tokens[-1]
        local_indices = sorted({t.segment for t in match.tokens})
        indices = [i + offset for i in local_indices]
        word_timing = all(t.start is not None and t.end is not None for t in match.tokens)
        start = first.start if word_timing else window[first.segment]["start"]
        end = last.end if word_timing else window[last.segment]["end"]
        parts = []
        for si in local_indices:
            local = [t for t in match.tokens if t.segment == si]
            parts.append(window[si]["text"][local[0].char_start:local[-1].char_end])
        phrase = " ".join(parts)
        key = match.spec.id + ":" + ":".join(t.id for t in match.tokens)
        stable_id = hashlib.sha256((context.fingerprint + ":" + match.spec.version + ":" + key).encode()).hexdigest()[:24]
        assumptions = list(match.assumptions)
        if first.segment != last.segment:
            assumptions.append("Words across adjacent transcript segments are treated as continuous because their timing passes the gap filter and no speaker change is known. This heuristic does not prove continuity.")
        if not word_timing:
            assumptions.append("Word timing is unavailable or stale; replay uses the whole segment.")
        if source_audio is None:
            assumptions.append("Source audio is unavailable; this is a reading opportunity only.")
        item = AnalysisResult(
            id=stable_id, rule_id=match.spec.id, rule_version=match.spec.version, category=match.spec.category,
            status="uncertain" if match.uncertain else "candidate", phrase=phrase,
            tokens=[t.reference() for t in match.tokens], segment_indices=indices, start=start, end=end,
            timing="words" if word_timing else "segment",
            timing_provenance="existing_asr_word_timestamps" if word_timing else "saved_segment_timestamps",
            source_audio=source_audio, transcript_fingerprint=context.fingerprint,
            pronunciations=[{"token_id": t.id, "alternatives": [p.as_dict() for p in t.pronunciations],
                             "supporting_variant_ids": [p.variant_id for p in support]}
                            for t, support in zip(match.tokens, match.supporting)],
            evidence_sources=[{"type": "saved_transcript", "fingerprint": context.fingerprint},
                              {"type": "pronunciation_dictionary", "version": provider.version},
                              {"type": "context_rule", "id": match.spec.id, "version": match.spec.version}],
            assumptions=assumptions, explanation=match.spec.explanation,
            target_token_ids=list(match.target_token_ids or tuple(t.id for t in match.tokens)),
            accent_note="American English listening opportunity; speaker, pace and emphasis vary. Not confirmed in the recording.",
        ).as_dict()
        item["notation"] = notation(match)
        # Equivalent rule/span matches share a card; distinct rule overlaps remain.
        if key in results:
            item["assumptions"] = list(dict.fromkeys(results[key]["assumptions"] + item["assumptions"]))
            item["target_token_ids"] = list(dict.fromkeys(results[key]["target_token_ids"] + item["target_token_ids"]))
            for old, current in zip(results[key]["pronunciations"], item["pronunciations"]):
                current["supporting_variant_ids"] = [v for v in current["supporting_variant_ids"] if v in old["supporting_variant_ids"]]
            item["notation"]["parts"] = results[key]["notation"]["parts"] + item["notation"]["parts"]
        results[key] = item
    patterns = sorted(results.values(), key=lambda p: (p["segment_index"], p["tokens"][0]["token_index"], p["rule_id"]))
    diagnostics = [d for d in context.diagnostics if segment_start <= d["segment_index"] < stop]
    requested_tokens = [t for t in context.tokens if segment_start <= t.segment + offset < stop]
    if view == "summary":
        fields = {"id", "rule_id", "category", "status", "label", "phrase", "tokens", "segment_indices",
                  "segment_index", "start", "end", "timing", "confidence", "evidence", "notation"}
        patterns = [{k: v for k, v in p.items() if k in fields} for p in patterns]
    return {"schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION,
            "dictionary_version": provider.version, "transcript_fingerprint": context.fingerprint,
            "view": view, "range": {"segment_start": segment_start, "segment_end": stop, "total_segments": len(segments)},
            "patterns": patterns, "coverage": {"token_count": len(requested_tokens),
                "dictionary_token_count": sum(bool(t.pronunciations) for t in requested_tokens),
                "diagnostics": diagnostics},
            "capabilities": capabilities(), "settings": {"max_boundary_gap_seconds": max_gap}}
