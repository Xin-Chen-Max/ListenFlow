"""Ensure text heuristics never masquerade as acoustic evidence."""

from speech_patterns import candidates


def test_candidates_use_aligned_phrase_times_and_explicit_uncertainty():
    segments = [{"start": 1, "end": 4, "text": "Did you listen?", "words": [
        {"word": " Did", "start": 1, "end": 1.3}, {"word": " you", "start": 1.3, "end": 1.6},
        {"word": " listen?", "start": 1.6, "end": 4}]}]
    item = candidates(segments)[0]
    assert (item["start"], item["end"], item["timing"]) == (1, 1.6, "words")
    assert item["label"] == "Possible pattern" and item["evidence"] == "text-rule"
    assert "actual recording" in item["explanation"]
    assert item["accent_note"]


def test_edited_text_without_alignment_uses_segment_replay():
    item = candidates([{"start": 5, "end": 8, "text": "I want to try.", "words": []}])[0]
    assert (item["start"], item["end"], item["timing"]) == (5, 8, "segment")


def test_repeated_occurrences_keep_their_own_timing():
    words = [{"word": w, "start": i, "end": i + .5} for i, w in enumerate(["did", "you", "did", "you"])]
    items = candidates([{"start": 0, "end": 4, "text": "Did you? Did you?", "words": words}])
    assert [p["start"] for p in items] == [0, 2]


def test_unmatched_text_makes_no_claim():
    assert candidates([{"start": 0, "end": 1, "text": "Hello world."}]) == []
