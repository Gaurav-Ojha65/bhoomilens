# Validation Rules

The validation engine is the **core differentiator** of BhoomiLens. It is intentionally deterministic — the LLM's job is to extract; Python's job is to decide whether the extraction is consistent with reference data.

---

## Rule catalog

Each rule emits an entry into `validation_flags[]` when it fires:

```json
{
  "issue_type": "AREA_MISMATCH",
  "severity": "HIGH",
  "field": "area",
  "expected": 2.5,
  "observed": 5.2,
  "expected_unit": "hectare",
  "observed_unit": "hectare",
  "reference_id": "REF-117-2-RAMPUR",
  "message": "Extracted area 5.2 ha differs from reference 2.5 ha by 108%"
}
```

| # | `issue_type` | Severity | Trigger |
|---|---|---|---|
| 1 | `MISSING_REQUIRED_FIELD` | HIGH | Any of `khasra_number`, `owner_name`, `village`, `state` is null/empty after extraction |
| 2 | `DUPLICATE_KHASRA` | HIGH | Another `records` row (not this one) has same `khasra_number` + `village_norm` within last 12 months |
| 3 | `OWNER_MISMATCH` | HIGH | Reference lookup by `(khasra, village)` returns a different owner (after normalization, see below) |
| 4 | `KHATA_MISMATCH` | MEDIUM | Extracted `khata_number` differs from reference for the same Khasra |
| 5 | `AREA_MISMATCH` | HIGH | `abs(observed_m2 - expected_m2) / expected_m2 > 0.10` (10% tolerance for OCR digit errors) |
| 6 | `UNIT_INCONSISTENCY` | MEDIUM | The extracted `area_unit` was inferred (missing from OCR) and the numeric magnitude implies a different unit (e.g., value `25000` with unit `hectare` is implausible) |
| 7 | `LOCATION_INCONSISTENCY` | MEDIUM | `(village, tehsil, district, state)` combination does not match any known reference row for this Khasra |
| 8 | `INVALID_NUMERIC_AREA` | HIGH | Area ≤ 0 or > 10000 hectares |
| 9 | `SUSPICIOUS_CHANGE` | HIGH | Same Khasra was updated recently with materially different fields (would-be mutation without registration_number) |
| 10 | `POSSIBLE_DUPLICATE_RECORD` | MEDIUM | Another record has the same `(owner_name_norm, khasra, area)` — likely a resubmission |
| 11 | `MUTATION_INCONSISTENCY` | MEDIUM | `mutation_date` is present but `registration_number` is not (or vice versa) |
| 12 | `LOW_OCR_CONFIDENCE` | LOW | `ocr_confidence < 0.6` on the entire document — informational, contributes to overall score but not a hard flag |

**Severities feed into confidence** — see `confidence.py`.

---

## Normalization before comparison

Before any comparison, values pass through `backend/shared/normalization.py`:

### Names

```
"राम प्रसाद"  ─┐
"Ram  Prasad" ─┼──▶  "ram prasad"    (transliterated + lower + collapsed)
"Ram Prashad" ─┘
```

Steps:
1. Strip surrounding whitespace, collapse internal whitespace
2. Unicode normalize (`NFKC`)
3. If contains Devanagari, transliterate via `indic-transliteration` (Sanscript) to `ITRANS` then to `IAST` normalized
4. Lowercase
5. Remove punctuation
6. Return canonical form for equality; **only exact match counts as `MATCH`**. Approximate matches (edit distance ≤ 2, or one transliteration variant) produce `NEEDS_REVIEW`, never `AUTO_APPROVED`.

We deliberately do **not** do aggressive fuzzy matching. The spec (Section 11) warns against it: "Do NOT make aggressive fuzzy matching decisions without exposing uncertainty."

### Khasra / Khata / Plot numbers

- Strip all whitespace
- Keep only `[0-9/\-]`
- Do **not** transliterate — these are numeric identifiers

Examples:
```
"117 / 2"     → "117/2"
"117-2"       → "117/2"    (dash treated as separator)
"११७/२"       → "117/2"    (Devanagari numerals mapped to ASCII)
```

### Area

Canonical unit: **square metres** (`m²`).

```
1 hectare      = 10000 m²
1 acre         = 4046.8564 m²
1 bigha (UP)   = 2508.38 m²        (state-dependent — see notes)
1 bigha (RJ)   = 2530.00 m²
1 katha (BR)   = 125 m²
1 gunta        = 101.171 m²
```

**Bigha and katha are state-dependent.** The normalization module uses the `state` field to pick the right conversion. If `state` is unknown at normalization time, the record is flagged `UNIT_INCONSISTENCY` and sent to review.

### Dates

Accept many formats, output `YYYY-MM-DD`:
- `12/03/1998` (assume DD/MM/YYYY for Indian docs)
- `12-3-98` → `1998-03-12` (assume 20th century for `98`)
- `१२/०३/१९९८` (Devanagari) → `1998-03-12`
- ISO 8601 — pass through

If ambiguous (e.g., `03/04/2005` — could be Mar 4 or Apr 3), emit `MUTATION_INCONSISTENCY` and keep the raw string in `field_confidence.mutation_date_raw`.

---

## Reference lookup

Primary key: `(khasra_number, village_norm)`.

```python
ref = reference_table.get_item(Key={
    "khasra_number": extracted.khasra_number,
    "village_norm": normalize_place(extracted.village),
}).get("Item")
```

If not found:
- Try Khasra alone (across all villages) — if there's exactly one hit, treat as match candidate but emit `LOCATION_INCONSISTENCY`
- If multiple hits, emit `POSSIBLE_DUPLICATE_RECORD` and don't auto-match

If `state` differs from reference `state`: emit `LOCATION_INCONSISTENCY` (HIGH severity — an entire state mismatch is nearly always an error).

---

## Duplicate detection

Two flavors:

**a) `DUPLICATE_KHASRA`** — same Khasra + village exists in `records` (not this record) with `validation_status IN (AUTO_APPROVED, HUMAN_APPROVED)` in the last 12 months. Uses `GSI3` on `validation_status + updated_at` scoped to a filter.

**b) `POSSIBLE_DUPLICATE_RECORD`** — same `(owner_name_norm, khasra, area)` — this is a resubmission of the same document. Distinct because it's not a *conflict*, just a duplicate submission.

---

## Confidence calculation

See `backend/shared/confidence.py`. Weights are **configurable via env** (per spec Section 12):

```python
overall_confidence = (
    WEIGHT_OCR         * ocr_score      +
    WEIGHT_EXTRACTION  * extraction_score +
    WEIGHT_VALIDATION  * validation_score
) * 100  # scale to 0..100

# Validation score:
validation_score = max(0.0, 1.0 - sum(severity_penalty(flag) for flag in flags))
# HIGH   = 0.35 penalty
# MEDIUM = 0.15
# LOW    = 0.05

# Decision:
if not flags_of_severity("HIGH") and overall_confidence >= THRESHOLD_AUTO_APPROVE:
    status = "AUTO_APPROVED"
elif overall_confidence < THRESHOLD_HIGH_RISK:
    status = "HIGH_RISK"          # < 70 by default
else:
    status = "NEEDS_REVIEW"       # 70 <= x < 90 or any HIGH flag
```

**Any HIGH-severity flag forces `NEEDS_REVIEW`** regardless of numeric score. This is intentional — you should not auto-approve a record with an area mismatch even if OCR was perfect.

Defaults (all configurable):

```
CONFIDENCE_WEIGHT_OCR=0.40
CONFIDENCE_WEIGHT_EXTRACTION=0.30
CONFIDENCE_WEIGHT_VALIDATION=0.30
THRESHOLD_AUTO_APPROVE=90
THRESHOLD_NEEDS_REVIEW=70    # below this → HIGH_RISK
```

These are **prototype thresholds**, not government standards. The dashboard makes this label explicit.
