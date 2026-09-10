#!/usr/bin/env python3
"""Offline evaluation of the validation engine against ground-truth scenarios.

Runs the validator directly against data/test_scenarios.json, comparing
predicted flags + status against expected ones. Produces a report that
scripts/README.md can paste into the main README's "Test results" section.

This does NOT hit AWS. It exercises the deterministic pieces of the
pipeline (normalization + validators) with mocked extraction confidences.
For end-to-end evaluation with real OCR + Bedrock, spin up the deployed
system and use --live-api.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.shared.confidence import (  # noqa: E402
    compute_overall_confidence,
    decide_status,
    policy_from_env,
)
from backend.shared.models import ExtractedRecord  # noqa: E402
from backend.shared.normalization import normalize_id, normalize_place  # noqa: E402
from backend.shared.validators import validate  # noqa: E402


# --- Load synthetic reference registry into an in-memory dict --------------

def _load_reference() -> dict:
    ref_path = REPO_ROOT / "data" / "reference_registry.json"
    with ref_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    index: dict[tuple[str, str], dict] = {}
    for r in payload.get("records", []):
        key = (normalize_id(r["khasra_number"]), normalize_place(r["village"]))
        r_copy = dict(r)
        r_copy["_ref_id"] = f"REF-{key[0]}-{key[1]}"
        index[key] = r_copy
    return index


def _make_lookups(reference_index: dict, preload_records: list):
    def _ref_lookup(khasra: str, village: str) -> Optional[dict]:
        return reference_index.get((khasra, village))

    def _khasra_only_lookup(khasra: str) -> list[dict]:
        return [v for (k, _), v in reference_index.items() if k == khasra]

    def _dup_lookup(khasra: str, village: str, exclude):
        return [
            r for r in preload_records
            if normalize_id(r["khasra_number"]) == khasra
            and normalize_place(r["village"]) == village
            and (not exclude or r.get("record_id") != exclude)
        ]

    return _ref_lookup, _khasra_only_lookup, _dup_lookup


# --- Run one scenario -------------------------------------------------------

def _run_scenario(scenario: dict, reference_index: dict, all_scenarios: list) -> dict:
    if scenario.get("starting_scenario"):
        base = next(s for s in all_scenarios if s["id"] == scenario["starting_scenario"])
        merged_extracted = dict(base["extracted"])
        merged_extracted.update(scenario.get("reviewer_correction", {}))
        ocr_conf = base["ocr_confidence"]
        ext_conf = base["extraction_confidence"]
        expected_flags = set(scenario.get("expected_flags_after_correction", []))
        expected_status = scenario.get("expected_status_after_correction")
        extracted = merged_extracted
    else:
        extracted = scenario["extracted"]
        ocr_conf = scenario["ocr_confidence"]
        ext_conf = scenario["extraction_confidence"]
        expected_flags = set(scenario.get("expected_flags", []))
        expected_status = scenario.get("expected_status")

    preload = scenario.get("preload_records", [])

    ref_lookup, khasra_only_lookup, dup_lookup = _make_lookups(reference_index, preload)
    rec = ExtractedRecord.from_dict(extracted)
    if rec.khasra_number:
        rec.khasra_number = normalize_id(rec.khasra_number)

    result = validate(
        rec,
        reference_lookup=ref_lookup,
        duplicate_lookup=dup_lookup,
        ocr_confidence=ocr_conf,
        khasra_only_lookup=khasra_only_lookup,
    )
    policy = policy_from_env()
    overall = compute_overall_confidence(
        ocr_confidence=ocr_conf,
        extraction_confidence=ext_conf,
        validation_score=result.validation_score,
        policy=policy,
    )
    status = decide_status(
        overall_confidence=overall, validation=result, policy=policy,
    )
    # For "after correction" scenarios, mirror the same rule as the records
    # Lambda: if no HIGH severity flags remain → HUMAN_APPROVED.
    if scenario.get("starting_scenario"):
        has_high = any(f.severity == "HIGH" for f in result.flags)
        status = "NEEDS_REVIEW" if has_high else "HUMAN_APPROVED"

    predicted_flags = {f.issue_type for f in result.flags}

    return {
        "id": scenario["id"],
        "title": scenario.get("title", ""),
        "expected_flags": sorted(expected_flags),
        "predicted_flags": sorted(predicted_flags),
        "expected_status": expected_status,
        "predicted_status": status,
        "overall_confidence": overall,
        "flag_pass": predicted_flags == expected_flags,
        "status_pass": status == expected_status,
    }


# --- Report -----------------------------------------------------------------

def _summarize(rows: list) -> dict:
    total = len(rows)
    flag_correct = sum(1 for r in rows if r["flag_pass"])
    status_correct = sum(1 for r in rows if r["status_pass"])
    per_flag_expected: Counter[str] = Counter()
    per_flag_predicted: Counter[str] = Counter()
    for r in rows:
        for f in r["expected_flags"]:
            per_flag_expected[f] += 1
        for f in r["predicted_flags"]:
            per_flag_predicted[f] += 1
    return {
        "total_scenarios": total,
        "flags_correct": flag_correct,
        "flag_accuracy": round(flag_correct / total, 4) if total else 0,
        "status_correct": status_correct,
        "status_accuracy": round(status_correct / total, 4) if total else 0,
        "expected_flag_counts": dict(per_flag_expected),
        "predicted_flag_counts": dict(per_flag_predicted),
    }


def main() -> int:
    # Windows default stdout is cp1252, which chokes on the arrows and other
    # non-ASCII glyphs in test scenario titles. Force UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=str(REPO_ROOT / "data" / "test_scenarios.json"))
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = ap.parse_args()

    with open(args.scenarios, "r", encoding="utf-8") as f:
        scenarios = json.load(f).get("scenarios", [])

    ref_index = _load_reference()
    rows = [_run_scenario(s, ref_index, scenarios) for s in scenarios]
    summary = _summarize(rows)

    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, indent=2))
        return 0

    print("=" * 72)
    print("BhoomiLens — validation engine evaluation report")
    print("=" * 72)
    for r in rows:
        flag_mark = "PASS" if r["flag_pass"] else "FAIL"
        status_mark = "PASS" if r["status_pass"] else "FAIL"
        print(f"[{flag_mark}/{status_mark}] {r['id']}  {r['title']}")
        if not r["flag_pass"]:
            print(f"    expected flags:  {r['expected_flags']}")
            print(f"    predicted flags: {r['predicted_flags']}")
        if not r["status_pass"]:
            print(f"    expected status: {r['expected_status']}")
            print(f"    predicted status:{r['predicted_status']} (confidence {r['overall_confidence']})")
    print("-" * 72)
    print(f"Scenarios:      {summary['total_scenarios']}")
    print(f"Flag accuracy:  {summary['flags_correct']}/{summary['total_scenarios']}"
          f"  ({summary['flag_accuracy']*100:.1f}%)")
    print(f"Status accuracy:{summary['status_correct']}/{summary['total_scenarios']}"
          f"  ({summary['status_accuracy']*100:.1f}%)")
    print("=" * 72)
    return 0 if summary["flags_correct"] == summary["total_scenarios"] else 1


if __name__ == "__main__":
    sys.exit(main())
