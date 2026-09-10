"""Application-level confidence + status decision.

Spec Section 12: we do NOT ask the LLM to invent a confidence number.
We combine three application-owned scores with configurable weights.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .models import (
    STATUS_AUTO_APPROVED,
    STATUS_HIGH_RISK,
    STATUS_NEEDS_REVIEW,
    SEVERITY_HIGH,
    ValidationResult,
)


@dataclass(frozen=True)
class ConfidencePolicy:
    weight_ocr: float = 0.40
    weight_extraction: float = 0.30
    weight_validation: float = 0.30
    threshold_auto_approve: float = 90.0   # >= this → AUTO_APPROVED
    threshold_needs_review: float = 70.0   # below this → HIGH_RISK
    force_review_on_high_severity: bool = True

    def normalized(self) -> "ConfidencePolicy":
        """Renormalize weights so they sum to 1.0. Idempotent."""
        total = self.weight_ocr + self.weight_extraction + self.weight_validation
        if total <= 0:
            raise ValueError("At least one weight must be positive")
        return ConfidencePolicy(
            weight_ocr=self.weight_ocr / total,
            weight_extraction=self.weight_extraction / total,
            weight_validation=self.weight_validation / total,
            threshold_auto_approve=self.threshold_auto_approve,
            threshold_needs_review=self.threshold_needs_review,
            force_review_on_high_severity=self.force_review_on_high_severity,
        )


def policy_from_env() -> ConfidencePolicy:
    """Read policy from env vars, falling back to defaults.

    Env vars:
      CONFIDENCE_WEIGHT_OCR
      CONFIDENCE_WEIGHT_EXTRACTION
      CONFIDENCE_WEIGHT_VALIDATION
      THRESHOLD_AUTO_APPROVE
      THRESHOLD_NEEDS_REVIEW
      FORCE_REVIEW_ON_HIGH_SEVERITY
    """
    def _f(name: str, default: float) -> float:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def _b(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in ("1", "true", "yes", "y")

    return ConfidencePolicy(
        weight_ocr=_f("CONFIDENCE_WEIGHT_OCR", 0.40),
        weight_extraction=_f("CONFIDENCE_WEIGHT_EXTRACTION", 0.30),
        weight_validation=_f("CONFIDENCE_WEIGHT_VALIDATION", 0.30),
        threshold_auto_approve=_f("THRESHOLD_AUTO_APPROVE", 90.0),
        threshold_needs_review=_f("THRESHOLD_NEEDS_REVIEW", 70.0),
        force_review_on_high_severity=_b("FORCE_REVIEW_ON_HIGH_SEVERITY", True),
    ).normalized()


def compute_overall_confidence(
    *,
    ocr_confidence: Optional[float],
    extraction_confidence: Optional[float],
    validation_score: float,
    policy: ConfidencePolicy,
) -> float:
    """Weighted 0..100 score."""
    ocr = 0.5 if ocr_confidence is None else max(0.0, min(1.0, float(ocr_confidence)))
    ext = 0.5 if extraction_confidence is None else max(0.0, min(1.0, float(extraction_confidence)))
    val = max(0.0, min(1.0, float(validation_score)))
    score = (
        policy.weight_ocr * ocr
        + policy.weight_extraction * ext
        + policy.weight_validation * val
    ) * 100.0
    return round(score, 2)


def decide_status(
    *,
    overall_confidence: float,
    validation: ValidationResult,
    policy: ConfidencePolicy,
) -> str:
    """Turn the numeric score + flags into a status label.

    Any HIGH-severity flag forces NEEDS_REVIEW regardless of score
    (unless `force_review_on_high_severity` is disabled — not recommended).
    """
    if policy.force_review_on_high_severity and validation.has_severity(SEVERITY_HIGH):
        return STATUS_NEEDS_REVIEW
    if overall_confidence >= policy.threshold_auto_approve:
        return STATUS_AUTO_APPROVED
    if overall_confidence < policy.threshold_needs_review:
        return STATUS_HIGH_RISK
    return STATUS_NEEDS_REVIEW
