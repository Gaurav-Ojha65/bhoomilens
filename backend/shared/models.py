"""Dataclasses + constants that describe a BhoomiLens record.

These are the schema the rest of the codebase agrees on. Kept explicit
(no Pydantic) to minimize Lambda cold-start cost and dependency count.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# ---- Statuses --------------------------------------------------------------

STATUS_PENDING = "PENDING"
STATUS_AUTO_APPROVED = "AUTO_APPROVED"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
STATUS_HIGH_RISK = "HIGH_RISK"
STATUS_HUMAN_APPROVED = "HUMAN_APPROVED"
STATUS_REJECTED = "REJECTED"

ALL_STATUSES = {
    STATUS_PENDING,
    STATUS_AUTO_APPROVED,
    STATUS_NEEDS_REVIEW,
    STATUS_HIGH_RISK,
    STATUS_HUMAN_APPROVED,
    STATUS_REJECTED,
}


# ---- Validation flag types -------------------------------------------------

FLAG_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
FLAG_DUPLICATE_KHASRA = "DUPLICATE_KHASRA"
FLAG_OWNER_MISMATCH = "OWNER_MISMATCH"
FLAG_KHATA_MISMATCH = "KHATA_MISMATCH"
FLAG_AREA_MISMATCH = "AREA_MISMATCH"
FLAG_UNIT_INCONSISTENCY = "UNIT_INCONSISTENCY"
FLAG_LOCATION_INCONSISTENCY = "LOCATION_INCONSISTENCY"
FLAG_INVALID_NUMERIC_AREA = "INVALID_NUMERIC_AREA"
FLAG_SUSPICIOUS_CHANGE = "SUSPICIOUS_CHANGE"
FLAG_POSSIBLE_DUPLICATE_RECORD = "POSSIBLE_DUPLICATE_RECORD"
FLAG_MUTATION_INCONSISTENCY = "MUTATION_INCONSISTENCY"
FLAG_LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"

SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"


REQUIRED_FIELDS = ("khasra_number", "owner_name", "village", "state")


@dataclass
class ValidationFlag:
    issue_type: str
    severity: str
    field: Optional[str] = None
    expected: Any = None
    observed: Any = None
    expected_unit: Optional[str] = None
    observed_unit: Optional[str] = None
    reference_id: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}


@dataclass
class ExtractedRecord:
    """Result of OCR + Bedrock extraction, before validation."""

    owner_name: Optional[str] = None
    father_or_spouse_name: Optional[str] = None
    khasra_number: Optional[str] = None
    khata_number: Optional[str] = None
    plot_number: Optional[str] = None
    area: Optional[float] = None
    area_unit: Optional[str] = None
    village: Optional[str] = None
    tehsil: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    land_classification: Optional[str] = None
    ownership_type: Optional[str] = None
    mutation_date: Optional[str] = None
    registration_number: Optional[str] = None
    field_confidence: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractedRecord":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class ValidationResult:
    flags: list[ValidationFlag] = field(default_factory=list)
    validation_score: float = 1.0  # 0..1
    reference_matched: bool = False
    reference_id: Optional[str] = None

    def add(self, flag: ValidationFlag) -> None:
        self.flags.append(flag)

    def to_dict(self) -> dict:
        return {
            "flags": [f.to_dict() for f in self.flags],
            "validation_score": round(self.validation_score, 4),
            "reference_matched": self.reference_matched,
            "reference_id": self.reference_id,
        }

    def has_severity(self, severity: str) -> bool:
        return any(f.severity == severity for f in self.flags)
