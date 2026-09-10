"""Deterministic validation rules.

The extraction LLM's job is to extract. The validator's job is to decide
whether that extraction is consistent with a reference registry.

Pure Python. No boto3. Reference lookups are passed in as callables so
this module is trivial to unit test.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from .models import (
    ExtractedRecord,
    ValidationFlag,
    ValidationResult,
    REQUIRED_FIELDS,
    FLAG_MISSING_REQUIRED_FIELD,
    FLAG_DUPLICATE_KHASRA,
    FLAG_OWNER_MISMATCH,
    FLAG_KHATA_MISMATCH,
    FLAG_AREA_MISMATCH,
    FLAG_UNIT_INCONSISTENCY,
    FLAG_LOCATION_INCONSISTENCY,
    FLAG_INVALID_NUMERIC_AREA,
    FLAG_MUTATION_INCONSISTENCY,
    FLAG_LOW_OCR_CONFIDENCE,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
)
from .normalization import (
    area_plausible,
    area_to_m2,
    normalize_id,
    normalize_name,
    normalize_place,
)


# Area mismatch tolerance: 10% (accounts for OCR digit slips like 2.5 vs 2.6)
AREA_TOLERANCE = 0.10

# Severity penalties feed into the validation_score (0..1)
_SEVERITY_PENALTY = {
    SEVERITY_HIGH: 0.35,
    SEVERITY_MEDIUM: 0.15,
    SEVERITY_LOW: 0.05,
}


# ---- Types for injected lookups --------------------------------------------

# ReferenceLookup: (khasra_normalized, village_normalized) -> dict | None
ReferenceLookup = Callable[[str, str], Optional[dict]]

# KhasraOnlyLookup: (khasra_normalized) -> list of reference rows across all villages.
# Optional. When supplied, lets us catch "khasra exists but in another village"
# even when the primary (khasra, village) lookup misses.
KhasraOnlyLookup = Callable[[str], Iterable[dict]]

# DuplicateLookup: (khasra_normalized, village_normalized, exclude_record_id) -> list[dict]
DuplicateLookup = Callable[[str, str, Optional[str]], Iterable[dict]]


# ---- Rules -----------------------------------------------------------------

def _check_required(rec: ExtractedRecord, result: ValidationResult) -> None:
    for f in REQUIRED_FIELDS:
        val = getattr(rec, f, None)
        if val is None or str(val).strip() == "":
            result.add(ValidationFlag(
                issue_type=FLAG_MISSING_REQUIRED_FIELD,
                severity=SEVERITY_HIGH,
                field=f,
                message=f"Required field '{f}' is missing or empty.",
            ))


def _check_invalid_area(rec: ExtractedRecord, result: ValidationResult) -> Optional[float]:
    """Convert to m² and flag impossible values. Returns m² or None."""
    if rec.area is None:
        return None
    if rec.area <= 0:
        result.add(ValidationFlag(
            issue_type=FLAG_INVALID_NUMERIC_AREA,
            severity=SEVERITY_HIGH,
            field="area",
            observed=rec.area,
            message="Area must be positive.",
        ))
        return None
    m2 = area_to_m2(rec.area, rec.area_unit, rec.state)
    if m2 is None:
        result.add(ValidationFlag(
            issue_type=FLAG_UNIT_INCONSISTENCY,
            severity=SEVERITY_MEDIUM,
            field="area_unit",
            observed=rec.area_unit,
            message=f"Unknown or unresolved area unit: {rec.area_unit!r}.",
        ))
        return None
    if not area_plausible(m2):
        result.add(ValidationFlag(
            issue_type=FLAG_INVALID_NUMERIC_AREA,
            severity=SEVERITY_HIGH,
            field="area",
            observed=rec.area,
            observed_unit=rec.area_unit,
            message=f"Area {m2:.1f} m² is outside plausible range for a single parcel.",
        ))
        return None
    return m2


def _check_reference_match(
    rec: ExtractedRecord,
    result: ValidationResult,
    reference_lookup: ReferenceLookup,
    khasra_only_lookup: Optional[KhasraOnlyLookup],
    extracted_area_m2: Optional[float],
) -> None:
    if not rec.khasra_number or not rec.village:
        return  # already flagged as missing required

    khasra_norm = normalize_id(rec.khasra_number)
    village_norm = normalize_place(rec.village)

    ref = reference_lookup(khasra_norm, village_norm)
    if ref is None:
        # (khasra, village) didn't match. If the Khasra exists in some OTHER
        # village, this is a location inconsistency, not "no reference".
        if khasra_only_lookup:
            other = list(khasra_only_lookup(khasra_norm))
            if other:
                other_villages = sorted({r.get("village") for r in other if r.get("village")})
                result.add(ValidationFlag(
                    issue_type=FLAG_LOCATION_INCONSISTENCY,
                    severity=SEVERITY_HIGH,
                    field="village",
                    expected=", ".join(v for v in other_villages if v),
                    observed=rec.village,
                    message=(
                        f"Khasra {rec.khasra_number} exists in reference registry "
                        f"but under village(s) {other_villages}, not '{rec.village}'."
                    ),
                ))
        return

    result.reference_matched = True
    result.reference_id = ref.get("_ref_id") or f"REF-{khasra_norm}-{village_norm}"

    # --- state mismatch (HIGH — a full state mismatch is nearly always error)
    if rec.state and ref.get("state"):
        if normalize_name(rec.state) != normalize_name(ref["state"]):
            result.add(ValidationFlag(
                issue_type=FLAG_LOCATION_INCONSISTENCY,
                severity=SEVERITY_HIGH,
                field="state",
                expected=ref["state"],
                observed=rec.state,
                reference_id=result.reference_id,
                message="Extracted state does not match reference state.",
            ))

    # --- district / tehsil (MEDIUM)
    for f in ("district", "tehsil"):
        obs = getattr(rec, f, None)
        exp = ref.get(f)
        if obs and exp and normalize_name(obs) != normalize_name(exp):
            result.add(ValidationFlag(
                issue_type=FLAG_LOCATION_INCONSISTENCY,
                severity=SEVERITY_MEDIUM,
                field=f,
                expected=exp,
                observed=obs,
                reference_id=result.reference_id,
                message=f"Extracted {f} does not match reference.",
            ))

    # --- owner mismatch (HIGH)
    if rec.owner_name and ref.get("owner_name"):
        if normalize_name(rec.owner_name) != normalize_name(ref["owner_name"]):
            result.add(ValidationFlag(
                issue_type=FLAG_OWNER_MISMATCH,
                severity=SEVERITY_HIGH,
                field="owner_name",
                expected=ref["owner_name"],
                observed=rec.owner_name,
                reference_id=result.reference_id,
                message="Owner name does not match reference after normalization.",
            ))

    # --- khata mismatch (MEDIUM)
    if rec.khata_number and ref.get("khata_number"):
        if normalize_id(rec.khata_number) != normalize_id(ref["khata_number"]):
            result.add(ValidationFlag(
                issue_type=FLAG_KHATA_MISMATCH,
                severity=SEVERITY_MEDIUM,
                field="khata_number",
                expected=ref["khata_number"],
                observed=rec.khata_number,
                reference_id=result.reference_id,
                message="Khata number differs from reference.",
            ))

    # --- area mismatch (HIGH)
    ref_area_m2 = ref.get("area_m2")
    if extracted_area_m2 is not None and ref_area_m2:
        rel = abs(extracted_area_m2 - float(ref_area_m2)) / float(ref_area_m2)
        if rel > AREA_TOLERANCE:
            result.add(ValidationFlag(
                issue_type=FLAG_AREA_MISMATCH,
                severity=SEVERITY_HIGH,
                field="area",
                expected=round(float(ref_area_m2), 2),
                observed=round(extracted_area_m2, 2),
                expected_unit="m²",
                observed_unit="m²",
                reference_id=result.reference_id,
                message=(
                    f"Extracted area {extracted_area_m2:.1f} m² differs from "
                    f"reference {float(ref_area_m2):.1f} m² by {rel*100:.1f}%."
                ),
            ))


def _check_duplicate(
    rec: ExtractedRecord,
    result: ValidationResult,
    duplicate_lookup: DuplicateLookup,
    current_record_id: Optional[str],
) -> None:
    if not rec.khasra_number or not rec.village:
        return
    khasra_norm = normalize_id(rec.khasra_number)
    village_norm = normalize_place(rec.village)
    dupes = list(duplicate_lookup(khasra_norm, village_norm, current_record_id))
    if not dupes:
        return
    result.add(ValidationFlag(
        issue_type=FLAG_DUPLICATE_KHASRA,
        severity=SEVERITY_HIGH,
        field="khasra_number",
        observed=rec.khasra_number,
        message=(
            f"{len(dupes)} approved record(s) already exist with this "
            "Khasra+village combination in the last 12 months."
        ),
    ))


def _check_mutation(rec: ExtractedRecord, result: ValidationResult) -> None:
    has_date = bool(rec.mutation_date)
    has_reg = bool(rec.registration_number)
    if has_date != has_reg:
        result.add(ValidationFlag(
            issue_type=FLAG_MUTATION_INCONSISTENCY,
            severity=SEVERITY_MEDIUM,
            field="mutation_date" if has_date else "registration_number",
            message=(
                "Mutation date is present but registration number is missing "
                "(or vice versa). A valid mutation should have both."
            ),
        ))


def _check_ocr_confidence(ocr_confidence: Optional[float], result: ValidationResult) -> None:
    if ocr_confidence is None:
        return
    if ocr_confidence < 0.6:
        result.add(ValidationFlag(
            issue_type=FLAG_LOW_OCR_CONFIDENCE,
            severity=SEVERITY_LOW,
            observed=round(ocr_confidence, 2),
            message=f"OCR confidence {ocr_confidence:.2f} is below 0.60 threshold.",
        ))


# ---- Entry point -----------------------------------------------------------

def validate(
    record: ExtractedRecord,
    *,
    reference_lookup: ReferenceLookup,
    duplicate_lookup: DuplicateLookup,
    ocr_confidence: Optional[float] = None,
    current_record_id: Optional[str] = None,
    khasra_only_lookup: Optional[KhasraOnlyLookup] = None,
) -> ValidationResult:
    """Run every validation rule against `record`.

    All external data access is injected as callables so the validator
    itself has zero I/O — every test can pass fake lookups.
    """
    result = ValidationResult()
    _check_required(record, result)
    extracted_area_m2 = _check_invalid_area(record, result)
    _check_reference_match(record, result, reference_lookup, khasra_only_lookup, extracted_area_m2)
    _check_duplicate(record, result, duplicate_lookup, current_record_id)
    _check_mutation(record, result)
    _check_ocr_confidence(ocr_confidence, result)

    # validation_score: 1.0 minus total severity penalty, clamped
    penalty = sum(_SEVERITY_PENALTY[f.severity] for f in result.flags)
    result.validation_score = max(0.0, 1.0 - penalty)
    return result
