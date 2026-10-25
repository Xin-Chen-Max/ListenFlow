"""Generic phone rules, timing guards and text-only evidence contracts."""

import pytest

from pronunciation.analysis import analyze
from pronunciation.context import TOKEN, build_context
from pronunciation.provider import dictionary
from speech_patterns import candidates


def segment(text, start=0, aligned=True, speaker=None):
    tokens = list(TOKEN.finditer(text))
    end = start + max(1, len(tokens))
    words = [{"word": m.group(), "start": start + i, "end": start + i + 1}
             for i, m in enumerate(tokens)] if aligned else []
    return {"start": start, "end": end, "text": text, "words": words, "speaker": speaker}


def matches(text, rule):
    return [p for p in candidates([segment(text)]) if p["rule_id"] == rule]


@pytest.mark.parametrize("rule,positive,negative", [
    ("linking.c_v", "need it", "turn back"),
    ("linking.c_v", "turn off", "need. It"),
    ("linking.v_v", "see it", "a university"),
    ("assimilation.yod", "did you", "did we"),
    ("assimilation.yod", "meet you", "meet. You"),
    ("reduction.function_word", "want to leave", "tomorrow begins"),
    ("reduction.function_word", "for a moment", "to"),
    ("elision.cluster_td", "kept moving", "last apple"),
    ("elision.cluster_td", "last night", "see night"),
    ("consonant.flap", "better", "attack"),
    ("consonant.flap", "get it", "get Tom"),
])
def test_each_rule_has_positive_and_negative_context(rule, positive, negative):
    assert matches(positive, rule)
    assert not matches(negative, rule)


@pytest.mark.parametrize("text,rule", [("need it", "linking.c_v"), ("turn off", "linking.c_v"),
    ("see it", "linking.v_v"), ("did you", "assimilation.yod"), ("want to", "reduction.function_word")])
def test_requested_phrases_without_phrase_specific_matching(text, rule):
    result = analyze([segment(text)], source_audio="/api/library/test/media")
    item = next(p for p in result["patterns"] if p["rule_id"] == rule)
    assert item["phrase"] == text and item["start"] == 0 and item["end"] == 2
    assert item["timing"] == "words" and item["source_audio"] == "/api/library/test/media"
    assert item["evidence_sources"][1]["type"] == "pronunciation_dictionary"


def test_sound_not_spelling_controls_boundaries():
    assert matches("an honest", "linking.c_v")  # silent h
    assert not matches("a university", "linking.v_v")  # initial Y
    assert matches("the hour", "linking.v_v")


def test_new_word_combinations_generalize():
    assert matches("bring apples", "linking.c_v")
    assert matches("fly over", "linking.v_v")
    assert matches("feed yourself", "assimilation.yod")


def test_alternatives_are_retained_and_eligibility_is_conditional():
    item = matches("get it", "consonant.flap")[0]
    assert item["status"] == "uncertain"
    right = item["pronunciations"][1]
    assert len(right["alternatives"]) == 2
    assert right["supporting_variant_ids"] == ["it(2)"]
    assert matches("last night", "elision.cluster_td")[0]["status"] == "uncertain"
    assert matches("need it", "linking.c_v")[0]["status"] == "candidate"
    assert any("stress" in a.lower() or "emphasis" in a.lower() for a in matches("better", "consonant.flap")[0]["assumptions"])


def test_weak_form_does_not_assert_wanna_or_sentence_stress():
    item = matches("want to leave", "reduction.function_word")[0]
    assert item["phrase"] == "want to" and item["status"] == "uncertain"
    assert "wanna" not in item["explanation"]
    assert any("neither is measured" in a for a in item["assumptions"])
    target = next(p for p in item["pronunciations"] if p["token_id"] in item["target_token_ids"])
    assert target["supporting_variant_ids"] == ["to(2)", "to(3)"]
    assert matches("for a moment", "reduction.function_word")


def test_grouped_function_words_keep_each_target_and_weak_variant_evidence():
    items = matches("for a", "reduction.function_word")
    assert len(items) == 1
    assert items[0]["target_token_ids"] == ["s0:t0", "s0:t1"]
    assert items[0]["pronunciations"][0]["supporting_variant_ids"] == ["for(2)", "for(3)"]
    assert items[0]["pronunciations"][1]["supporting_variant_ids"] == ["a"]


def test_token_identity_curly_contractions_case_and_original_offsets():
    seg = segment("Don’t NEED it, don't need it.")
    context = build_context([seg], dictionary())
    assert context.tokens[0].normalized == "don't"
    assert context.tokens[0].text == "Don’t"
    assert context.tokens[0].pronunciations
    items = [p for p in candidates([seg]) if p["rule_id"] == "linking.c_v" and p["phrase"].lower() == "need it"]
    assert [p["start"] for p in items] == [1, 4]
    assert items[0]["id"] != items[1]["id"]
    token = items[0]["tokens"][0]
    assert seg["text"][token["char_start"]:token["char_end"]] == "NEED"


def test_unknown_and_unsupported_tokens_have_explicit_coverage_not_guesses():
    result = analyze([segment("need zzqxunknown it 2026 café well-known")])
    reasons = {d["reason"] for d in result["coverage"]["diagnostics"]}
    assert reasons == {"unknown_word", "unsupported_normalization"}
    assert not result["patterns"]
    assert result["coverage"]["dictionary_token_count"] == 2


def test_edits_and_invalid_alignment_fall_back_without_fabricated_word_times():
    seg = segment("need it")
    seg["text"] = "turn off"
    item = candidates([seg])[0]
    assert item["timing"] == "segment" and (item["start"], item["end"]) == (0, 2)
    assert "stale" in " ".join(item["assumptions"])
    assert analyze([seg])["transcript_fingerprint"] != analyze([segment("need it")])["transcript_fingerprint"]


def test_missing_words_and_legacy_audio_are_honest():
    item = candidates([segment("need it", start=5, aligned=False)])[0]
    assert (item["start"], item["end"], item["timing"]) == (5, 7, "segment")
    assert item["source_audio"] is None and any("unavailable" in a for a in item["assumptions"])


def test_cross_segment_reuses_existing_word_times_and_indices():
    result = analyze([segment("need", 0), segment("it", 1.2)])
    item = next(p for p in result["patterns"] if p["rule_id"] == "linking.c_v")
    assert item["segment_indices"] == [0, 1] and item["segment_index"] == 0
    assert (item["start"], item["end"], item["timing"]) == (0, 2.2, "words")
    assert any("heuristic" in a for a in item["assumptions"])


@pytest.mark.parametrize("case", ["punctuation", "speaker", "gap", "overlap", "no_words", "stale_words", "nan", "outside", "empty_middle"])
def test_cross_segment_guards(case):
    left, right = segment("need", 0), segment("it", 1.2)
    segs = [left, right]
    if case == "punctuation": left["text"] = "need."
    elif case == "speaker": left["speaker"], right["speaker"] = "A", "B"
    elif case == "gap": right.update(segment("it", 1.251))
    elif case == "overlap": right.update(segment("it", .9))
    elif case == "no_words": left["words"] = []
    elif case == "stale_words": left["words"][0]["word"] = "turn"
    elif case == "nan": left["words"][0]["start"] = float("nan")
    elif case == "outside": left["words"][0]["end"] = 4
    elif case == "empty_middle": segs.insert(1, {"text": "", "start": 1, "end": 1.1})
    assert not analyze(segs)["patterns"]


def test_gap_is_configurable_and_known_within_segment_pause_blocks_boundary():
    segs = [segment("need", 0), segment("it", 1.3)]
    assert not analyze(segs)["patterns"]
    assert analyze(segs, max_gap=.31)["patterns"]
    with pytest.raises(ValueError): analyze(segs, max_gap=-1)
    seg = segment("need it")
    seg["words"][0]["end"] = .5
    assert not analyze([seg])["patterns"]


def test_null_word_speakers_do_not_hide_a_known_segment_speaker_change():
    segs = [segment("need", 0, speaker="A"), segment("it", 1.1, speaker="B")]
    for seg in segs:
        seg["words"][0]["speaker"] = None
    assert not analyze(segs)["patterns"]


@pytest.mark.parametrize("boundary", [".", "!", "?", ";", ":", "\n"])
def test_strong_punctuation_blocks_within_segment_pairs(boundary):
    assert not matches("need" + boundary + " it", "linking.c_v")


def test_unmatched_text_makes_no_acoustic_claim_and_results_are_stable():
    assert candidates([segment("Hello world.")]) == []
    result = analyze([segment("Did you get it? Better for a moment.")])
    assert result == analyze([segment("Did you get it? Better for a moment.")])
    items = result["patterns"]
    assert len({p["id"] for p in items}) == len(items)
    assert all(p["status"] in {"candidate", "uncertain"} and p["confidence"] is None for p in items)
    assert all(p["label"] == "Possible pattern" and p["evidence"] == "text-rule" and p["confidence_reason"] for p in items)
    assert all(p["transcript_fingerprint"] == result["transcript_fingerprint"] for p in items)
    assert result["capabilities"]["acoustically_verified"] == []
    assert result["capabilities"]["stages"]["mfa"] == "interface only"


def test_distinct_overlapping_opportunities_remain():
    items = candidates([segment("get it")])
    assert {p["rule_id"] for p in items} == {"linking.c_v", "consonant.flap"}


def test_invalid_segment_timing_has_diagnostic_and_no_replay_candidate():
    seg = segment("better need it")
    seg["end"] = -1
    result = analyze([seg])
    assert not result["patterns"]
    assert any(d["reason"] == "invalid_segment_timing" for d in result["coverage"]["diagnostics"])
