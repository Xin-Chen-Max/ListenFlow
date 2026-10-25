"""Illustrative listening cues from supporting phones, never measured audio."""

from .inventory import IPA, VOWELS, base, stress
from .rules import Match


def _ipa(phones):
    return "".join("ə" if p == "AH0" else "ɚ" if p == "ER0" else IPA[base(p)] for p in phones)


def notation(match: Match) -> dict:
    # Choosing an example is distinct from selecting a pronunciation as observed.
    phones = [variants[0].phones for variants in match.supporting]
    rule = match.spec.id
    label, parts = match.spec.title, []
    if rule in {"linking.c_v", "linking.v_v"}:
        label = "Link" if rule == "linking.c_v" else "Vowel link"
        parts = [{"text": "/" + _ipa(phones[0]), "kind": "text"}, {"text": "‿", "kind": "link"},
                 {"text": _ipa(phones[1]) + "/", "kind": "text"}]
    elif rule == "assimilation.yod":
        label = "Combine"
        final = base(phones[0][-1])
        parts = [{"text": f"/{IPA[final]} + j/ → /{'tʃ' if final == 'T' else 'dʒ'}/", "kind": "text"}]
    elif rule == "reduction.function_word":
        label = "Weak form"
        for token, variants in zip(match.tokens, match.supporting):
            if token.id in match.target_token_ids:
                example = next((p for p in variants if "AH0" in p.phones), variants[0])
                parts.append({"text": token.text + " → /" + _ipa(example.phones) + "/", "kind": "text"})
    elif rule == "elision.cluster_td":
        label = "Possible omission"
        parts = [{"text": "/" + _ipa(phones[0][:-1]), "kind": "text"},
                 {"text": _ipa(phones[0][-1:]), "kind": "omission"},
                 {"text": " " + _ipa(phones[1]) + "/", "kind": "text"}]
    elif rule == "consonant.flap":
        label = "Tap"
        left = list(phones[0])
        if len(phones) == 2:
            parts = [{"text": "/" + _ipa(left[:-1]) + "ɾ" + _ipa(phones[1]) + "/", "kind": "text"}]
        else:
            rendered = []
            for i, phone in enumerate(left):
                eligible = (0 < i < len(left)-1 and base(phone) in {"T", "D"} and
                            base(left[i-1]) in VOWELS and stress(left[i-1]) in {1, 2} and stress(left[i+1]) == 0)
                rendered.append("ɾ" if eligible else _ipa([phone]))
            parts = [{"text": "/" + "".join(rendered) + "/", "kind": "text"}]
    return {"label": label, "parts": parts, "illustrative": True,
            "note": "One possible pronunciation example from dictionary phones; stress marks omitted. Not verified in audio."}
