#!/usr/bin/env python3
"""Load data/reference_registry.json into the BhoomiLens reference DynamoDB table.

Usage:
  python scripts/seed_reference_data.py \
    --table bhoomilens-reference \
    --file data/reference_registry.json \
    --region ap-south-1

Every record is written with source="SYNTHETIC_DEMO" — a defensive
double-check that no one accidentally uploads real citizen data here.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO_ROOT / "data" / "reference_registry.json"


def _to_ddb(value):
    if isinstance(value, list):
        return [_to_ddb(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_ddb(v) for k, v in value.items()}
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="bhoomilens-reference")
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--region", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        payload = json.load(f)
    records = payload.get("records", [])

    print(f"Loading {len(records)} synthetic reference records into {args.table} …")

    if args.dry_run:
        for r in records[:3]:
            print(json.dumps(r, indent=2, ensure_ascii=False))
        print("… dry-run, no writes")
        return 0

    session = boto3.Session(region_name=args.region) if args.region else boto3.Session()
    table = session.resource("dynamodb").Table(args.table)

    written = 0
    with table.batch_writer() as batch:
        for r in records:
            if r.get("source") != "SYNTHETIC_DEMO":
                r["source"] = "SYNTHETIC_DEMO"  # enforce
            item = _to_ddb(r)
            batch.put_item(Item=item)
            written += 1
    print(f"Done. Wrote {written} records to {args.table}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
