"""Offline pronunciation provider. Unknown words are never guessed."""

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path
import re
from typing import Protocol

from .inventory import broad_ipa, valid

COMMIT = "74790861f652b15e4ac49015a90074ad62a27690"
SHA256 = "81917843c7f44ce2b094ac63873c2c7a4cf802040792c455ba3ca406891c3d22"
DATA = Path(__file__).parent / "data" / "cmudict" / "cmudict.dict"


@dataclass(frozen=True)
class Pronunciation:
    variant_id: str
    phones: tuple[str, ...]
    source: str = "cmudict"

    def as_dict(self) -> dict:
        return {"variant_id": self.variant_id, "phones": list(self.phones),
                "broad_ipa": broad_ipa(self.phones), "source": self.source}


class PronunciationProvider(Protocol):
    """Later G2P providers must report provenance and every retained alternative."""
    version: str

    def lookup(self, normalized: str) -> tuple[Pronunciation, ...]: ...


class CmuDictionary:
    version = "cmudict@" + COMMIT

    def __init__(self, path: Path = DATA):
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError("The bundled pronunciation dictionary failed its integrity check.")
        entries: dict[str, list[Pronunciation]] = {}
        for line in data.decode("utf-8").splitlines():
            body = line.split("#", 1)[0].strip()
            if not body:
                continue
            word, *phones = body.split()
            if not phones or not all(valid(p) for p in phones):
                raise ValueError("Unsupported phone in bundled dictionary: " + word)
            key = re.sub(r"\(\d+\)$", "", word)
            entries.setdefault(key, []).append(Pronunciation(word, tuple(phones)))
        self._entries = {key: tuple(value) for key, value in entries.items()}

    def lookup(self, normalized: str) -> tuple[Pronunciation, ...]:
        return self._entries.get(normalized, ())


@lru_cache(maxsize=1)
def dictionary() -> CmuDictionary:
    return CmuDictionary()
