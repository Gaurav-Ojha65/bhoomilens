"""Tests for backend.shared.validators.

Reference/duplicate lookups are injected as callables, so these tests
run entirely offline — no boto3, no moto required.
"""

from __future__ import annotations

import pytest

from backend.shared.models import (
    ExtractedRecord,
    FLAG_AREA_MISMATCH,
    FLAG_DUPLICATE_KHASRA,
    FLAG_INVALID_NUMERIC_AREA,
    FLAG_KHATA_MISMATCH,
    FLAG_LOCATION_INCONSISTENCY,
    FLAG_LOW_OCR_CONFIDENCE,
    FLAG_MISSING_REQUIRED_FIELD,
    FLAG_MUTATION_INCONSISTENCY,
    FLAG_OWNER_MISMATCH,
    FLAG_UNIT_INCONSISTENCY,
    SEVERITY_HIGH,
)
from backend.shared.validators import validate


# ---- Fixtures / helpers ----------------------------------------------------

_REF_117_2_RAMPUR = {
    "khasra_number": "117/2",
    "village_norm": "rampur",
    "village": "Rampur",
    "owner_name": "Ram Prasad",
    "khata_number": "284",
    "area_m2": 25000.0,
    "district": "Lucknow",
    "state": "Uttar Pradesh",
    "_ref_id": "REF-117-2-RAMPUR",
}


def _lookup_by_ref(khasra_norm: str, village_norm: str):
    if (khasra_norm, village_norm) == ("117/2", "rampur"):
        return _REF_117_2_RAMPUR
    return None


def _no_duplicates(khasra_norm, village_norm, exclude):
    return []


def _one_duplicate(khasra_norm, village_norm, exclude):
    return [{"record_id": "OTHER", "khasra_number": khasra_norm, "village_norm": village_norm}]


def _make_record(**overrides):
    base = dict(
        owner_name="Ram Prasad",
        khasra_number="117/2",
        khata_number="284",
        area=2.5,
        area_unit="hectare",
        village="Rampur",
        state="Uttar Pradesh",
    )
    base.update(overrides)
    return ExtractedRecord(**base)


def _flag_types(result):
    return [f.issue_type for f in result.flags]


# ---- Individual rules ------------------------------------------------------

class TestRequiredFields:
    def test_missing_khasra_flagged(self):
        rec = _make_record(khasra_number=None)
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_MISSING_REQUIRED_FIELD in _flag_types(result)

    def test_all_present_no_missing_flag(self):
        result = validate(_make_record(), reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_MISSING_REQUIRED_FIELD not in _flag_types(result)


class TestAreaValidation:
    def test_matching_area_no_flag(self):
        result = validate(_make_record(), reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_AREA_MISMATCH not in _flag_types(result)

    def test_area_mismatch(self):
        rec = _make_record(area=5.2)  # 5.2 ha vs 2.5 ha reference
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_AREA_MISMATCH in _flag_types(result)

    def test_area_within_tolerance(self):
        rec = _make_record(area=2.6)  # ~4% over — inside 10% tolerance
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_AREA_MISMATCH not in _flag_types(result)

    def test_area_unit_conversion(self):
        rec = _make_record(area=25000, area_unit="square meter")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_AREA_MISMATCH not in _flag_types(result)

    def test_invalid_area_zero(self):
        rec = _make_record(area=0)
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_INVALID_NUMERIC_AREA in _flag_types(result)

    def test_impossible_area(self):
        rec = _make_record(area=11000)  # 11000 hectare on one Khasra
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_INVALID_NUMERIC_AREA in _flag_types(result)

    def test_unknown_unit_flags_unit_inconsistency(self):
        rec = _make_record(area_unit="furlong-sq")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_UNIT_INCONSISTENCY in _flag_types(result)


class TestOwnerAndKhata:
    def test_owner_mismatch(self):
        rec = _make_record(owner_name="Sunita Sharma")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_OWNER_MISMATCH in _flag_types(result)

    def test_owner_hindi_matches_english(self):
        rec = _make_record(owner_name="राम प्रसाद")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_OWNER_MISMATCH not in _flag_types(result)

    def test_khata_mismatch(self):
        rec = _make_record(khata_number="999")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_KHATA_MISMATCH in _flag_types(result)


class TestLocation:
    def test_state_mismatch(self):
        rec = _make_record(state="Madhya Pradesh")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_LOCATION_INCONSISTENCY in _flag_types(result)

    def test_district_mismatch(self):
        rec = _make_record(district="Kanpur")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_LOCATION_INCONSISTENCY in _flag_types(result)


class TestDuplicates:
    def test_duplicate_khasra(self):
        result = validate(_make_record(), reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_one_duplicate)
        assert FLAG_DUPLICATE_KHASRA in _flag_types(result)


class TestMutation:
    def test_date_without_registration(self):
        rec = _make_record(mutation_date="2019-06-14")  # no registration_number
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_MUTATION_INCONSISTENCY in _flag_types(result)

    def test_both_present_no_flag(self):
        rec = _make_record(mutation_date="2019-06-14", registration_number="R-1")
        result = validate(rec, reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert FLAG_MUTATION_INCONSISTENCY not in _flag_types(result)


class TestOcrConfidence:
    def test_low_ocr_flagged(self):
        result = validate(_make_record(), reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates,
                          ocr_confidence=0.4)
        assert FLAG_LOW_OCR_CONFIDENCE in _flag_types(result)

    def test_high_ocr_not_flagged(self):
        result = validate(_make_record(), reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates,
                          ocr_confidence=0.95)
        assert FLAG_LOW_OCR_CONFIDENCE not in _flag_types(result)


class TestValidationScore:
    def test_clean_record_score_one(self):
        result = validate(_make_record(), reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates,
                          ocr_confidence=0.9)
        assert result.validation_score == 1.0
        assert result.flags == []

    def test_area_mismatch_reduces_score(self):
        result = validate(_make_record(area=5.2), reference_lookup=_lookup_by_ref,
                          duplicate_lookup=_no_duplicates)
        assert result.validation_score < 1.0
        assert result.has_severity(SEVERITY_HIGH)

    def test_score_clamped_at_zero(self):
        # Many high-severity flags stacked
        rec = ExtractedRecord()  # no required fields → 4x HIGH
        result = validate(rec, reference_lookup=lambda a, b: None,
                          duplicate_lookup=_no_duplicates)
        assert result.validation_score == 0.0
