"""Pronunciation data, licensing, contracts and inventory invariants."""

import hashlib
import pytest

from pronunciation.contracts import AnalysisResult
from pronunciation.inventory import INVENTORY, broad_ipa, valid
from pronunciation.provider import DATA, SHA256, dictionary
from pronunciation.taxonomy import RULES, TAXONOMY, capabilities


def test_dictionary_integrity_license_and_complete_inventory():
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == SHA256
    assert hashlib.sha256(DATA.with_name("LICENSE").read_bytes()).hexdigest() == "bd4ce8e44170a5f9f481310ca85c51de3c4f851a65e679b40e603b143bd3542a"
    assert len(INVENTORY) == 39
    assert valid("AH0") and valid("T")
    assert not valid("AH") and not valid("T1") and not valid("AX0")


def test_all_alternatives_preserved_without_guessing_or_stress_loss():
    provider = dictionary()
    assert [p.phones for p in provider.lookup("to")] == [("T", "UW1"), ("T", "IH0"), ("T", "AH0")]
    assert [p.variant_id for p in provider.lookup("read")] == ["read", "read(2)"]
    assert provider.lookup("don't") and provider.lookup("zzqxunknown") == ()
    assert broad_ipa(("B", "EH1", "T", "ER0")) == "b ˈɛ t ɚ"


def test_taxonomy_registry_is_complete_but_not_all_supported():
    assert set(TAXONOMY) == {"linking", "reduction", "elision", "assimilation", "consonant_phenomena", "prosody"}
    assert len({r.id for r in RULES}) == 6
    assert all(r.version and r.prerequisites and r.limitations and r.explanation for r in RULES)
    assert capabilities()["acoustically_verified"] == []


@pytest.mark.parametrize("status", ["observed", "not_observed"])
def test_text_serializer_rejects_acoustic_statuses(status):
    item = AnalysisResult("id", "rule", "1", "linking", status, "phrase", [], [0], 0, 1, "segment", "segment", None,
                          "fingerprint", [], [], [], "explanation", "accent")
    with pytest.raises(ValueError, match="acoustic"):
        item.as_dict()
