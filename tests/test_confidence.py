"""Tests for backend.shared.confidence."""

from __future__ import annotations

import pytest

from backend.shared.confidence import (
    ConfidencePolicy,
    compute_overall_confidence,
    decide_status,
    policy_from_env,
)
from backend.shared.models import (
    STATUS_AUTO_APPROVED,
    STATUS_HIGH_RISK,
    STATUS_NEEDS_REVIEW,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    ValidationFlag,
    ValidationResult,
)


DEFAULT = ConfidencePolicy().normalized()


class TestPolicyNormalization:
    def test_weights_sum_to_one(self):
        p = ConfidencePolicy(weight_ocr=1, weight_extraction=1, weight_validation=1).normalized()
        assert p.weight_ocr + p.weight_extraction + p.weight_validation == pytest.approx(1.0)

    def test_reject_all_zero_weights(self):
        with pytest.raises(ValueError):
            ConfidencePolicy(weight_ocr=0, weight_extraction=0, weight_validation=0).normalized()


class TestOverallConfidence:
    def test_perfect_inputs(self):
        assert compute_overall_confidence(
            ocr_confidence=1.0,
            extraction_confidence=1.0,
            validation_score=1.0,
            policy=DEFAULT,
        ) == 100.0

    def test_zero_inputs(self):
        assert compute_overall_confidence(
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            validation_score=0.0,
            policy=DEFAULT,
        ) == 0.0

    def test_none_treated_as_half(self):
        # default weights 0.4 / 0.3 / 0.3; validation=1 → score = 0.4*0.5 + 0.3*0.5 + 0.3*1 = 0.65
        assert compute_overall_confidence(
            ocr_confidence=None,
            extraction_confidence=None,
            validation_score=1.0,
            policy=DEFAULT,
        ) == 65.0

    def test_weight_change(self):
        p = ConfidencePolicy(weight_ocr=1, weight_extraction=0, weight_validation=0).normalized()
        assert compute_overall_confidence(
            ocr_confidence=0.5,
            extraction_confidence=1.0,
            validation_score=1.0,
            policy=p,
        ) == 50.0


class TestDecideStatus:
    def _vr(self, *flag_severities):
        vr = ValidationResult(validation_score=1.0)
        for sev in flag_severities:
            vr.add(ValidationFlag(issue_type="X", severity=sev))
        return vr

    def test_auto_approve_when_high_and_no_high_flag(self):
        assert decide_status(overall_confidence=92.0, validation=self._vr(), policy=DEFAULT) == STATUS_AUTO_APPROVED

    def test_needs_review_when_middle(self):
        assert decide_status(overall_confidence=75.0, validation=self._vr(), policy=DEFAULT) == STATUS_NEEDS_REVIEW

    def test_high_risk_when_low(self):
        assert decide_status(overall_confidence=50.0, validation=self._vr(), policy=DEFAULT) == STATUS_HIGH_RISK

    def test_high_severity_forces_review_even_at_100(self):
        assert decide_status(
            overall_confidence=100.0,
            validation=self._vr(SEVERITY_HIGH),
            policy=DEFAULT,
        ) == STATUS_NEEDS_REVIEW

    def test_medium_severity_does_not_force_review(self):
        assert decide_status(
            overall_confidence=95.0,
            validation=self._vr(SEVERITY_MEDIUM),
            policy=DEFAULT,
        ) == STATUS_AUTO_APPROVED

    def test_disable_forced_review(self):
        p = ConfidencePolicy(force_review_on_high_severity=False).normalized()
        assert decide_status(
            overall_confidence=95.0,
            validation=self._vr(SEVERITY_HIGH),
            policy=p,
        ) == STATUS_AUTO_APPROVED


class TestPolicyFromEnv:
    def test_defaults_when_no_env(self, monkeypatch):
        for k in (
            "CONFIDENCE_WEIGHT_OCR", "CONFIDENCE_WEIGHT_EXTRACTION",
            "CONFIDENCE_WEIGHT_VALIDATION", "THRESHOLD_AUTO_APPROVE",
            "THRESHOLD_NEEDS_REVIEW", "FORCE_REVIEW_ON_HIGH_SEVERITY",
        ):
            monkeypatch.delenv(k, raising=False)
        p = policy_from_env()
        assert p.threshold_auto_approve == 90.0
        assert p.threshold_needs_review == 70.0
        assert p.force_review_on_high_severity is True

    def test_reads_overrides(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_WEIGHT_OCR", "0.6")
        monkeypatch.setenv("CONFIDENCE_WEIGHT_EXTRACTION", "0.2")
        monkeypatch.setenv("CONFIDENCE_WEIGHT_VALIDATION", "0.2")
        monkeypatch.setenv("THRESHOLD_AUTO_APPROVE", "85")
        p = policy_from_env()
        assert p.threshold_auto_approve == 85.0
        assert p.weight_ocr == pytest.approx(0.6)
