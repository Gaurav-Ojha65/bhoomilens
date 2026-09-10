"""Tests for backend.shared.normalization.

These tests are pure — no AWS, no network.
Run: python -m pytest tests/test_normalization.py -v
"""

from __future__ import annotations

import pytest

from backend.shared.normalization import (
    area_plausible,
    area_to_m2,
    is_devanagari,
    normalize_date,
    normalize_id,
    normalize_name,
    normalize_place,
    normalize_whitespace,
)


class TestWhitespace:
    def test_collapses_inner_whitespace(self):
        assert normalize_whitespace("Ram  \t Prasad\n") == "Ram Prasad"

    def test_empty_string(self):
        assert normalize_whitespace("   ") == ""


class TestDevanagariDetection:
    def test_detects_hindi(self):
        assert is_devanagari("राम प्रसाद") is True

    def test_ignores_latin(self):
        assert is_devanagari("Ram Prasad") is False


class TestNormalizeName:
    def test_lowercase_and_strip(self):
        assert normalize_name("  Ram   PRASAD  ") == "ram prasad"

    def test_removes_punctuation(self):
        assert normalize_name("Ram Prasad, S/O Shyam.") == "ram prasad s o shyam"

    def test_hindi_matches_english(self):
        # Uses either indic-transliteration OR the hint map fallback.
        assert normalize_name("राम प्रसाद") == normalize_name("Ram Prasad")

    def test_empty_returns_empty(self):
        assert normalize_name(None) == ""
        assert normalize_name("") == ""


class TestNormalizeId:
    def test_slash_and_dash_are_equivalent(self):
        assert normalize_id("117-2") == "117/2"
        assert normalize_id("117 / 2") == "117/2"
        assert normalize_id("117/2") == "117/2"

    def test_devanagari_digits(self):
        assert normalize_id("११७/२") == "117/2"

    def test_upper_case_letter_suffix(self):
        assert normalize_id("12a") == "12A"
        assert normalize_id("101/2a") == "101/2A"

    def test_strips_extraneous(self):
        assert normalize_id(" #117/2 ") == "117/2"

    def test_none_returns_empty(self):
        assert normalize_id(None) == ""


class TestAreaConversion:
    def test_hectare_to_m2(self):
        assert area_to_m2(2.5, "hectare") == 25000.0

    def test_acre_to_m2(self):
        assert area_to_m2(1, "acre") == pytest.approx(4046.8564, rel=1e-4)

    def test_square_meter_passthrough(self):
        assert area_to_m2(500, "square meter") == 500.0

    def test_bigha_uttar_pradesh(self):
        # UP bigha ~ 2508.38 m²
        assert area_to_m2(2, "bigha", "Uttar Pradesh") == pytest.approx(5016.76, rel=1e-4)

    def test_bigha_rajasthan(self):
        assert area_to_m2(2, "bigha", "Rajasthan") == pytest.approx(5060.0, rel=1e-4)

    def test_katha_bihar(self):
        assert area_to_m2(2, "katha", "Bihar") == 250.0

    def test_unknown_unit_returns_none(self):
        assert area_to_m2(1, "furlong-squared") is None

    def test_none_inputs(self):
        assert area_to_m2(None, "hectare") is None
        assert area_to_m2(1, None) is None


class TestAreaPlausibility:
    def test_normal_area(self):
        assert area_plausible(25000) is True

    def test_zero_not_plausible(self):
        assert area_plausible(0) is False

    def test_too_large(self):
        assert area_plausible(2_000_000_000) is False


class TestDateNormalization:
    def test_ddmmyyyy(self):
        assert normalize_date("14/06/2019") == "2019-06-14"

    def test_isolike(self):
        assert normalize_date("2019-06-14") == "2019-06-14"

    def test_dev_digits(self):
        assert normalize_date("१२/०३/१९९८") == "1998-03-12"

    def test_two_digit_year_20th(self):
        assert normalize_date("12/3/98") == "1998-03-12"

    def test_two_digit_year_21st(self):
        assert normalize_date("12/3/05") == "2005-03-12"

    def test_invalid_returns_none(self):
        assert normalize_date("not a date") is None
        assert normalize_date("13/13/2020") is None  # month 13
