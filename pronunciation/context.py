"""Original-text tokens and conservative, provenance-preserving replay context."""

from dataclasses import dataclass, field
import hashlib
import json
import math
import re

from .provider import Pronunciation, PronunciationProvider

TOKEN = re.compile(r"\w+(?:['’\-]\w+)*", re.UNICODE)
STRONG_BOUNDARY = re.compile(r"[.!?;:\n\r]")
NORMALIZED = re.compile(r"[a-z]+(?:'[a-z]+)*\Z")
DEFAULT_GAP_SECONDS = .250


def normalize(text: str) -> str:
    return text.lower().replace("’", "'")


def interval(start, end) -> bool:
    return (all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in (start, end))
            and 0 <= start < end)


@dataclass
class Token:
    id: str
    segment: int
    index: int
    text: str
    normalized: str
    char_start: int
    char_end: int
    pronunciations: tuple[Pronunciation, ...]
    start: float | None = None
    end: float | None = None
    speaker: str | int | None = None
    segment_offset: int = 0

    def reference(self) -> dict:
        return {"id": self.id, "segment_index": self.segment + self.segment_offset, "token_index": self.index,
                "text": self.text, "normalized": self.normalized,
                "char_start": self.char_start, "char_end": self.char_end}


@dataclass
class Context:
    segments: list[dict]
    tokens: list[Token]
    pairs: list[tuple[Token, Token]]
    fingerprint: str
    diagnostics: list[dict] = field(default_factory=list)


def transcript_fingerprint(segments: list[dict]) -> str:
    relevant = [{key: s.get(key) for key in ("text", "start", "end", "words", "speaker")} for s in segments]
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def build_context(segments: list[dict], provider: PronunciationProvider,
                  max_gap: float = DEFAULT_GAP_SECONDS, segment_offset: int = 0) -> Context:
    if not math.isfinite(max_gap) or max_gap < 0:
        raise ValueError("The continuity gap must be a finite nonnegative number.")
    fingerprint = transcript_fingerprint(segments)
    tokens, diagnostics = [], []
    for si, seg in enumerate(segments):
        text = seg.get("text", "")
        current = []
        valid_segment = interval(seg.get("start"), seg.get("end"))
        if not valid_segment:
            diagnostics.append({"segment_index": si + segment_offset, "reason": "invalid_segment_timing"})
        for ti, match in enumerate(TOKEN.finditer(text)):
            normalized = normalize(match.group())
            supported = bool(NORMALIZED.fullmatch(normalized))
            variants = provider.lookup(normalized) if supported else ()
            token = Token(f"s{si + segment_offset}:t{ti}", si, ti, match.group(), normalized, *match.span(), variants,
                          speaker=seg.get("speaker"), segment_offset=segment_offset)
            current.append(token)
            if not variants:
                diagnostics.append({**token.reference(), "reason": "unknown_word" if supported else "unsupported_normalization"})

        words = seg.get("words") or []
        # Accept timing only if the entire sequence still corresponds to the saved text.
        aligned = valid_segment and bool(current) and len(words) == len(current)
        previous_end = seg.get("start")
        if aligned:
            for token, word in zip(current, words):
                matches = list(TOKEN.finditer(word.get("word", "")))
                start, end = word.get("start"), word.get("end")
                if (len(matches) != 1 or normalize(matches[0].group()) != token.normalized or
                    not interval(start, end) or start < previous_end - .001 or
                    start < seg["start"] - .001 or end > seg["end"] + .001):
                    aligned = False
                    break
                previous_end = end
        if aligned:
            for token, word in zip(current, words):
                token.start, token.end = word["start"], word["end"]
                token.speaker = word.get("speaker") if word.get("speaker") is not None else seg.get("speaker")
        elif current:
            diagnostics.append({"segment_index": si + segment_offset, "reason": "word_timing_unavailable_or_stale",
                                "replay": "segment" if valid_segment else "unavailable"})
        tokens.extend(current)

    pairs = []
    for left, right in zip(tokens, tokens[1:]):
        ls, rs = segments[left.segment], segments[right.segment]
        if not interval(ls.get("start"), ls.get("end")) or not interval(rs.get("start"), rs.get("end")):
            continue
        if right.segment == left.segment:
            separator = ls["text"][left.char_end:right.char_start]
        elif right.segment == left.segment + 1:
            if left.end is None or right.start is None:
                continue
            separator = ls["text"][left.char_end:] + rs["text"][:right.char_start]
        else:
            continue
        if STRONG_BOUNDARY.search(separator):
            continue
        if left.speaker is not None and right.speaker is not None and left.speaker != right.speaker:
            continue
        if left.end is not None and right.start is not None:
            gap = right.start - left.end
            if gap < -.001 or gap > max_gap + 1e-9:
                continue
        if left.pronunciations and right.pronunciations:
            pairs.append((left, right))
    return Context(segments, tokens, pairs, fingerprint, diagnostics)
