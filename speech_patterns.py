"""Text-rule learning candidates. This module does not analyze recorded phonetics."""

import re

RULES = [
    (r"\bdid\s+you\b", "Sound combination", "In some fluent speech, the d and y may combine into a sound like j. Compare the actual recording before drawing a conclusion.", "Speaker- and accent-dependent."),
    (r"\bwould\s+you\b", "Sound combination", "The d and y may combine in fluent speech. Listen to this boundary and compare it with a careful reading.", "Speaker- and accent-dependent."),
    (r"\bwant\s+to\b", "Reduction", "In casual speech, want to may be reduced toward wanna. The written phrase alone cannot tell us whether that happened here.", "Common in some informal varieties; a careful pronunciation is also valid."),
    (r"\bgoing\s+to\b", "Reduction", "When describing an intention, going to may be reduced toward gonna. Check the meaning and the audio; movement uses may behave differently.", "Informal speech; varies by speaker and context."),
    (r"\bget\s+it\b", "Possible flap", "In some North American speech, the t may sound like a quick tap, closer to a brief d. Stress and context affect this.", "Primarily a North American English listening cue, not a pronunciation requirement."),
    (r"\b(?:pick|look|turn|take|put|in|on)\s+(?:a|an|it|up|out|off|in|on)\b", "Linking", "The final consonant of the first word may connect smoothly to the vowel at the start of the next word. Replay the boundary and listen for yourself.", "Linking varies with accent, pace, emphasis, and pauses."),
]


def candidates(segments: list[dict]) -> list[dict]:
    result = []
    for index, seg in enumerate(segments):
        for regex, category, explanation, accent in RULES:
            for match in re.finditer(regex, seg["text"], re.IGNORECASE):
                start, end, timing = seg["start"], seg["end"], "segment"
                tokens = match.group().lower().split()
                words = seg.get("words") or []
                normalized = [re.sub(r"[^a-z]", "", w["word"].lower()) for w in words]
                prefix = re.findall(r"[a-z]+", seg["text"][:match.start()].lower())
                offset = len(prefix)
                if normalized[offset:offset + len(tokens)] == tokens:
                    start, end = words[offset]["start"], words[offset + len(tokens) - 1]["end"]
                    timing = "words"
                result.append({"segment_index": index, "phrase": match.group(), "category": category,
                               "label": "Possible pattern", "evidence": "text-rule",
                               "explanation": explanation, "accent_note": accent,
                               "start": start, "end": end, "timing": timing})
    return result
