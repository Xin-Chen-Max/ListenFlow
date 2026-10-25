"""Compatibility facade for local dictionary-backed text opportunities."""

from pronunciation.analysis import analyze


def candidates(segments: list[dict]) -> list[dict]:
    return analyze(segments)["patterns"]
