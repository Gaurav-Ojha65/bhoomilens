"""Record + audit writes.

Kept in one module so both the SFN persist Lambda and the REST records
Lambda share the same write path — same fields, same audit shape.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import boto3

from .dynamo import to_ddb
from .normalization import normalize_name

_dynamodb = boto3.resource("dynamodb")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_record_id() -> str:
    """A ULID-like sortable ID. Using timestamp-hex + uuid suffix keeps deps low."""
    ts_ms = int(time.time() * 1000)
    return f"REC-{ts_ms:013d}-{uuid.uuid4().hex[:8]}"


def new_document_id() -> str:
    return uuid.uuid4().hex


def put_pending_record(*, record_id: str, document_id: str,
                       source_document_key: str, uploaded_by: str) -> None:
    table = _dynamodb.Table(os.environ["RECORDS_TABLE"])
    now = _now_iso()
    table.put_item(Item={
        "record_id": record_id,
        "document_id": document_id,
        "source_document_key": source_document_key,
        "uploaded_by": uploaded_by,
        "validation_status": "PENDING",
        "created_at": now,
        "updated_at": now,
    })


def upsert_processed_record(processed: dict) -> dict:
    """Write the result of the SFN pipeline. Idempotent per record_id."""
    table = _dynamodb.Table(os.environ["RECORDS_TABLE"])
    record_id = processed["record_id"]
    extracted = processed.get("extracted") or {}
    now = _now_iso()

    item: dict[str, Any] = {
        "record_id": record_id,
        "document_id": processed.get("document_id"),
        "validation_status": processed["validation_status"],
        "overall_confidence": processed["overall_confidence"],
        "validation_score": processed["validation_score"],
        "validation_flags": processed["validation_flags"],
        "reference_matched": processed.get("reference_matched", False),
        "reference_id": processed.get("reference_id"),
        "ocr_confidence": processed.get("ocr_confidence"),
        "extraction_confidence": processed.get("extraction_confidence"),
        "updated_at": now,
    }

    # Copy extracted fields onto the top-level item so GSIs work.
    for k in ("owner_name", "father_or_spouse_name", "khasra_number",
              "khata_number", "plot_number", "area", "area_unit",
              "village", "tehsil", "district", "state",
              "land_classification", "ownership_type",
              "mutation_date", "registration_number",
              "field_confidence"):
        if k in extracted:
            item[k] = extracted[k]
    if extracted.get("village"):
        item["village_norm"] = extracted.get("village_norm") or normalize_name(extracted["village"])
    if extracted.get("owner_name"):
        item["owner_name_norm"] = normalize_name(extracted["owner_name"])

    # Preserve created_at if the row already exists
    resp = table.get_item(Key={"record_id": record_id})
    existing = resp.get("Item") or {}
    item["created_at"] = existing.get("created_at", now)
    for k in ("source_document_key", "uploaded_by"):
        if k in existing:
            item[k] = existing[k]

    table.put_item(Item=to_ddb(item))
    return item


def apply_correction(record_id: str, changes: dict, user: str) -> dict:
    """Merge changes into a record and return the merged dict (no revalidation here)."""
    table = _dynamodb.Table(os.environ["RECORDS_TABLE"])
    resp = table.get_item(Key={"record_id": record_id})
    if "Item" not in resp:
        raise KeyError(record_id)
    row = resp["Item"]
    merged = dict(row)
    for k, v in changes.items():
        merged[k] = v
    merged["updated_at"] = _now_iso()
    if "owner_name" in changes:
        merged["owner_name_norm"] = normalize_name(changes["owner_name"] or "")
    if "village" in changes:
        merged["village_norm"] = normalize_name(changes["village"] or "")
    table.put_item(Item=to_ddb(merged))
    return merged


def write_audit(*, record_id: str, action: str, user: str,
                field: Optional[str] = None,
                old_value: Any = None, new_value: Any = None,
                note: Optional[str] = None) -> None:
    table = _dynamodb.Table(os.environ["AUDIT_TABLE"])
    item = {
        "record_id": record_id,
        "timestamp": _now_iso(),
        "action": action,
        "user": user,
    }
    if field is not None:
        item["field"] = field
    if old_value is not None:
        item["old_value"] = str(old_value)
    if new_value is not None:
        item["new_value"] = str(new_value)
    if note:
        item["note"] = note
    table.put_item(Item=to_ddb(item))
