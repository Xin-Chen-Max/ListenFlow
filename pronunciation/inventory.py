"""CMU's 39 base phones, with lexical vowel stress retained separately."""

VOWELS = frozenset("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split())
CONSONANTS = frozenset("B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH".split())
INVENTORY = VOWELS | CONSONANTS
IPA = dict(zip(
    "AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH".split(),
    "ɑ æ ʌ ɔ aʊ aɪ ɛ ɝ eɪ ɪ i oʊ ɔɪ ʊ u b tʃ d ð f ɡ h dʒ k l m n ŋ p ɹ s ʃ t θ v w j z ʒ".split(),
))


def base(phone: str) -> str:
    return phone.rstrip("012")


def stress(phone: str) -> int | None:
    return int(phone[-1]) if phone[-1:] in {"0", "1", "2"} else None


def valid(phone: str) -> bool:
    symbol = base(phone)
    return symbol in INVENTORY and (phone in CONSONANTS or (symbol in VOWELS and stress(phone) is not None))


def broad_ipa(phones: tuple[str, ...]) -> str:
    # A display of dictionary segments and lexical stress, not a narrow transcription.
    return " ".join(("ˈ" if stress(p) == 1 else "ˌ" if stress(p) == 2 else "") +
                    ("ə" if p == "AH0" else "ɚ" if p == "ER0" else IPA[base(p)]) for p in phones)
