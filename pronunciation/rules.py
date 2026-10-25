"""Phone-environment detectors. No phrase list and no recorded-sound claims."""

from dataclasses import dataclass
from itertools import product

from .context import Context, Token, interval
from .inventory import CONSONANTS, VOWELS, base, stress
from .provider import Pronunciation
from .taxonomy import RULES, RuleSpec

# This lexical class is deliberately small. It is not a phrase matcher or POS tagger.
FUNCTION_WORDS = frozenset("a an and at can for from of or the to".split())
CLUSTER_PRECEDERS = frozenset("S Z F V SH ZH N L P K B G M NG".split())


@dataclass
class Match:
    spec: RuleSpec
    tokens: tuple[Token, ...]
    supporting: tuple[tuple[Pronunciation, ...], ...]
    uncertain: bool
    assumptions: tuple[str, ...] = ()
    target_token_ids: tuple[str, ...] = ()


def _has_weak(phones):
    return any(stress(p) == 0 for p in phones) and not any(stress(p) in {1, 2} for p in phones)


def _has_strong(phones):
    return any(stress(p) in {1, 2} for p in phones)


def _internal_flap(phones):
    return any(base(phones[i]) in {"T", "D"} and base(phones[i-1]) in VOWELS and
               stress(phones[i-1]) in {1, 2} and base(phones[i+1]) in VOWELS and stress(phones[i+1]) == 0
               for i in range(1, len(phones)-1))


def _pair_match(rule_id, left, right):
    last, first = base(left[-1]), base(right[0])
    if rule_id == "linking.c_v":
        return last in CONSONANTS and first in VOWELS
    if rule_id == "linking.v_v":
        return last in VOWELS and first in VOWELS
    if rule_id == "assimilation.yod":
        return last in {"T", "D"} and first == "Y"
    if rule_id == "elision.cluster_td":
        return len(left) >= 2 and last in {"T", "D"} and base(left[-2]) in CLUSTER_PRECEDERS and first in CONSONANTS
    if rule_id == "consonant.flap":
        return (len(left) >= 2 and last in {"T", "D"} and base(left[-2]) in VOWELS and
                stress(left[-2]) in {1, 2} and first in VOWELS and stress(right[0]) == 0)
    return False


def detect(context: Context) -> list[Match]:
    matches = []
    for spec in RULES:
        if spec.id == "reduction.function_word":
            # Context only selects a replay span, never a presumed grammatical parse.
            neighbors = {}
            for left, right in context.pairs:
                neighbors.setdefault(left.id, (left, right))
                neighbors[right.id] = (left, right)
            for token in context.tokens:
                if token.normalized not in FUNCTION_WORDS or token.id not in neighbors:
                    continue
                weak = [p for p in token.pronunciations if _has_weak(p.phones)]
                strong = [p for p in token.pronunciations if _has_strong(p.phones)]
                if weak and strong:
                    span = neighbors[token.id]
                    support = tuple(tuple(weak) if t.id == token.id else t.pronunciations for t in span)
                    matches.append(Match(spec, span, support, True,
                                         ("A grammatical use and lack of contrastive emphasis are assumed; neither is measured.",), (token.id,)))
        else:
            for left, right in context.pairs:
                variants = list(product(left.pronunciations, right.pronunciations))
                supported = [(a, b) for a, b in variants if _pair_match(spec.id, a.phones, b.phones)]
                if supported:
                    support = tuple(tuple(p for p in t.pronunciations if any(p == pair[i] for pair in supported))
                                    for i, t in enumerate((left, right)))
                    conditional = spec.id in {"consonant.flap", "elision.cluster_td", "assimilation.yod"}
                    assumptions = ("Sentence emphasis, speaking rate and actual realization are unknown.",) if conditional else ()
                    if len(supported) != len(variants):
                        assumptions += ("Only some dictionary pronunciation combinations support this environment; no alternative was selected as the recorded pronunciation.",)
                    matches.append(Match(spec, (left, right), support, conditional or len(supported) != len(variants), assumptions))
            if spec.id == "consonant.flap":
                for token in context.tokens:
                    seg = context.segments[token.segment]
                    if not interval(seg.get("start"), seg.get("end")):
                        continue
                    support = tuple(p for p in token.pronunciations if _internal_flap(p.phones))
                    if support:
                        assumptions = ("Dictionary lexical stress is known; sentence emphasis and realization are not.",)
                        if len(support) != len(token.pronunciations):
                            assumptions += ("Only some dictionary alternatives support this environment.",)
                        matches.append(Match(spec, (token,), (support,), True, assumptions))
    return matches
