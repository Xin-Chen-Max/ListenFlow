"""Stable taxonomy and declarative rule metadata, independent of UI labels."""

from dataclasses import asdict, dataclass

TAXONOMY = {
    "linking": "Linking", "reduction": "Reduction", "elision": "Elision",
    "assimilation": "Assimilation", "consonant_phenomena": "Consonant phenomena", "prosody": "Prosody",
}


@dataclass(frozen=True)
class RuleSpec:
    id: str
    category: str
    title: str
    explanation: str
    prerequisites: tuple[str, ...]
    limitations: tuple[str, ...]
    version: str = "1.0"


RULES = (
    RuleSpec("linking.c_v", "linking", "Consonant to vowel linking",
             "The final consonant may connect smoothly to the next vowel. Listen for one continuous phrase rather than a new start.",
             ("dictionary final consonant and initial vowel", "continuous word boundary"), ("A pause or emphasis can prevent linking.",)),
    RuleSpec("linking.v_v", "linking", "Vowel to vowel transition",
             "Two neighboring vowel sounds may flow together, sometimes with a brief glide. Listen to the transition without assuming an extra consonant occurred.",
             ("dictionary vowel sounds on both sides", "continuous word boundary"), ("Glide choice and realization are not inferred.",)),
    RuleSpec("assimilation.yod", "assimilation", "T or D plus Y",
             "A final t or d followed by a y sound may combine toward ch or j in fluent speech. Compare the actual recording with a careful reading.",
             ("final T or D followed by Y", "continuous word boundary"), ("Rate, emphasis and speaker variety affect coalescence.",)),
    RuleSpec("reduction.function_word", "reduction", "Function-word weak form",
             "This grammatical word has a dictionary weak pronunciation. Listen for a shorter or less prominent vowel when it is unstressed; a strong form is also valid.",
             ("grammatical-word lexicon", "dictionary strong and weak alternatives", "neighboring context"),
             ("Grammatical role and sentence emphasis are not measured.",)),
    RuleSpec("elision.cluster_td", "elision", "Final cluster simplification",
             "In a consonant cluster before another consonant, final t or d may be omitted. Replay and compare; a quiet or unreleased stop is not proof of deletion.",
             ("eligible final consonant plus T/D cluster", "following consonant"),
             ("Deletion, masking and an unreleased stop cannot be distinguished from text.",)),
    RuleSpec("consonant.flap", "consonant_phenomena", "American English flap opportunity",
             "Between suitable vowel sounds, t or d may become a quick tongue tap, often heard as a brief d. Listen for the tap; stress and word boundaries matter.",
             ("intervocalic T/D", "preceding stressed vowel", "following unstressed vowel"),
             ("Lexical stress does not measure sentence emphasis.", "This conservative rule omits other flap environments.")),
)


def capabilities() -> dict:
    return {"text_candidates": [asdict(rule) for rule in RULES],
            "taxonomy": TAXONOMY, "unsupported": ["prosody", "other assimilation and consonant processes", "G2P inference"],
            "experimental": ["conditional stress and variant-dependent candidates", "250 ms continuity filter"],
            "acoustically_verified": [],
            "stages": {"existing_asr_words": "available timing only", "whisperx": "interface only",
                       "mfa": "interface only", "acoustic_verifier": "unavailable"}}
