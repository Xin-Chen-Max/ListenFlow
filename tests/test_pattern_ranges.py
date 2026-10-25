"""Bounded text analysis must preserve full-result IDs, evidence and boundaries."""

import pytest

from pronunciation.analysis import analyze
from pronunciation.context import TOKEN


def segment(text, start):
    words = [{"word": m.group(), "start": start + i, "end": start + i + 1}
             for i, m in enumerate(TOKEN.finditer(text))]
    return {"text": text, "start": start, "end": words[-1]["end"], "words": words}


def test_ranges_equal_full_results_including_cross_segment_weak_form_choices():
    segments = [segment(text, i) for i, text in enumerate(["need", "it", "for", "a", "to", "get", "it"])]
    full = analyze(segments)
    for i in range(len(segments)):
        page = analyze(segments, segment_start=i, segment_limit=1)
        expected = [p for p in full["patterns"] if i in p["segment_indices"]]
        assert page["patterns"] == expected
        assert page["transcript_fingerprint"] == full["transcript_fingerprint"]
        assert page["coverage"]["token_count"] == 1
        assert all(t["segment_index"] == int(t["id"].split(":")[0][1:]) for p in page["patterns"] for t in p["tokens"])


def test_summary_omits_heavy_details_without_changing_identity_status_or_replay():
    segments = [segment("need it", 0)]
    full = analyze(segments, segment_limit=1)
    short = analyze(segments, segment_limit=1, view="summary")
    assert short["view"] == "summary"
    for a, b in zip(full["patterns"], short["patterns"]):
        assert {k: a[k] for k in b} == b
        assert b["confidence"] is None and b["label"] == "Possible pattern"
        assert "pronunciations" not in b and "evidence_sources" not in b and "explanation" not in b


@pytest.mark.parametrize("phrase,rule,label", [("need it", "linking.c_v", "Link"),
    ("see it", "linking.v_v", "Vowel link"), ("did you", "assimilation.yod", "Combine"),
    ("want to", "reduction.function_word", "Weak form"), ("kept moving", "elision.cluster_td", "Possible omission"),
    ("better", "consonant.flap", "Tap")])
def test_every_notation_is_explicitly_illustrative(phrase, rule, label):
    pattern = next(p for p in analyze([segment(phrase, 0)])["patterns"] if p["rule_id"] == rule)
    cue = pattern["notation"]
    assert cue["illustrative"] and cue["label"] == label and cue["parts"]
    assert "Not verified in audio" in cue["note"]
    assert pattern["status"] in {"candidate", "uncertain"}
    omitted = [p["text"] for p in cue["parts"] if p["kind"] == "omission"]
    assert omitted == (["t"] if rule == "elision.cluster_td" else [])


def test_notation_uses_weak_example_and_keeps_all_dictionary_alternatives():
    pattern = next(p for p in analyze([segment("want to", 0)])["patterns"] if p["rule_id"] == "reduction.function_word")
    assert pattern["notation"]["parts"] == [{"text": "to → /tə/", "kind": "text"}]
    assert len(pattern["pronunciations"][1]["alternatives"]) == 3


def test_range_coverage_excludes_neighboring_unknown_tokens():
    segments = [segment("zzqxunknown", 0), segment("need it", 1), segment("café", 3)]
    result = analyze(segments, segment_start=1, segment_limit=1)
    assert result["coverage"]["token_count"] == 2
    assert result["coverage"]["diagnostics"] == []


@pytest.mark.parametrize("kwargs", [{"segment_start": -1}, {"segment_limit": 0}, {"segment_limit": 49}, {"view": "unknown"}])
def test_invalid_range_and_view_are_rejected(kwargs):
    with pytest.raises(ValueError):
        analyze([segment("need it", 0)], **kwargs)
