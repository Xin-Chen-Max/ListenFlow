"""Contracts for future aligners/verifiers. No model is installed or run here."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

PatternStatus = Literal["candidate", "uncertain", "observed", "not_observed"]


@dataclass(frozen=True)
class StageProvenance:
    provider: str
    version: str
    model: str | None
    inventory: str
    validated_for: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignedUnit:
    token_id: str
    label: str
    start: float
    end: float


@dataclass(frozen=True)
class AlignmentResult:
    units: tuple[AlignedUnit, ...]
    provenance: StageProvenance
    source_audio: str
    transcript_fingerprint: str
    # Adapters own only their scratch files, never the retained source recording.
    owned_temporary_files: tuple[str, ...] = ()


class WordAligner(Protocol):
    def align_words(self, source_audio: str, segments: list[dict], fingerprint: str) -> AlignmentResult: ...


class PhoneAligner(Protocol):
    def align_phones(self, source_audio: str, tokens: list[dict], fingerprint: str) -> AlignmentResult: ...


class AcousticVerifier(Protocol):
    """Alignment alone cannot implement this separately validated capability."""
    provenance: StageProvenance

    def verify(self, source_audio: str, opportunity: dict, alignment: AlignmentResult) -> dict: ...


@dataclass
class AnalysisResult:
    """Shared result envelope. This serializer only accepts text-stage statuses."""
    id: str
    rule_id: str
    rule_version: str
    category: str
    status: PatternStatus
    phrase: str
    tokens: list[dict]
    segment_indices: list[int]
    start: float
    end: float
    timing: str
    timing_provenance: str
    source_audio: str | None
    transcript_fingerprint: str
    pronunciations: list[dict]
    evidence_sources: list[dict]
    assumptions: list[str]
    explanation: str
    accent_note: str
    target_token_ids: list[str] = field(default_factory=list)
    confidence: None = field(default=None, init=False)

    def as_dict(self) -> dict:
        from dataclasses import asdict
        if self.status not in {"candidate", "uncertain"}:
            raise ValueError("Text analysis cannot emit an acoustic verification status.")
        result = asdict(self)
        result.update(segment_index=self.segment_indices[0], label="Possible pattern", evidence="text-rule",
                      confidence_reason="Uncalibrated text/dictionary rule; no acoustic probability is available.")
        return result
