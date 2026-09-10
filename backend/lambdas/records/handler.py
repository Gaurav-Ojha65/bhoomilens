"""REST handler for /records, /records/{id}, PUT /records/{id},
/records/{id}/approve|reject|revalidate.

One Lambda handles all record routes so the code paths that share
revalidation logic stay in one file.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key

from backend.shared.confidence import compute_overall_confidence, decide_status, policy_from_env
from backend.shared.dynamo import from_ddb
from backend.shared.http import (
    err,
    get_body,
    get_caller_identity,
    get_path_param,
    get_query_param,
    ok,
)
from backend.shared.models import (
    ExtractedRecord,
    STATUS_HUMAN_APPROVED,
    STATUS_REJECTED,
)
from backend.shared.persistence import apply_correction, write_audit
from backend.shared.portals import lookup_portal
from backend.shared.validators import validate
from backend.shared.normalization import normalize_id, normalize_place

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")
_s3 = boto3.client("s3")
RECORDS_TABLE = os.environ["RECORDS_TABLE"]
REFERENCE_TABLE = os.environ["REFERENCE_TABLE"]
DOCUMENTS_BUCKET = os.environ["DOCUMENTS_BUCKET"]

EDITABLE_FIELDS = (
    "owner_name", "father_or_spouse_name", "khasra_number", "khata_number",
    "plot_number", "area", "area_unit", "village", "tehsil", "district",
    "state", "land_classification", "ownership_type", "mutation_date",
    "registration_number",
)


# ---- Reference / duplicate lookups (same as validation Lambda) ------------

def _reference_lookup(khasra_norm: str, village_norm: str) -> Optional[dict]:
    table = _dynamodb.Table(REFERENCE_TABLE)
    try:
        r = table.get_item(Key={"khasra_number": khasra_norm, "village_norm": village_norm})
    except Exception:
        logger.exception("Reference lookup failed")
        return None
    return r.get("Item")


def _duplicate_lookup(khasra_norm: str, village_norm: str, exclude_record_id: Optional[str]):
    table = _dynamodb.Table(RECORDS_TABLE)
    for status in ("AUTO_APPROVED", "HUMAN_APPROVED"):
        try:
            resp = table.query(
                IndexName="GSI3",
                KeyConditionExpression=Key("validation_status").eq(status),
                FilterExpression=(
                    Attr("khasra_number").eq(khasra_norm)
                    & Attr("village_norm").eq(village_norm)
                ),
                Limit=25,
            )
        except Exception:
            logger.exception("Duplicate lookup failed")
            continue
        for item in resp.get("Items", []):
            if exclude_record_id and item.get("record_id") == exclude_record_id:
                continue
            yield item


def _record_from_row(row: dict) -> ExtractedRecord:
    return ExtractedRecord.from_dict({k: row.get(k) for k in row.keys()})


def _revalidate(row: dict) -> dict:
    rec = _record_from_row(row)
    if rec.khasra_number:
        rec.khasra_number = normalize_id(rec.khasra_number)
    result = validate(
        rec,
        reference_lookup=_reference_lookup,
        duplicate_lookup=_duplicate_lookup,
        ocr_confidence=float(row.get("ocr_confidence") or 0),
        current_record_id=row.get("record_id"),
    )
    policy = policy_from_env()
    overall = compute_overall_confidence(
        ocr_confidence=float(row.get("ocr_confidence") or 0),
        extraction_confidence=float(row.get("extraction_confidence") or 0),
        validation_score=result.validation_score,
        policy=policy,
    )
    status = decide_status(
        overall_confidence=overall, validation=result, policy=policy,
    )
    # Human-approved records stay approved unless the reviewer touched fields
    return {
        "validation_flags": [f.to_dict() for f in result.flags],
        "validation_score": result.validation_score,
        "overall_confidence": overall,
        "validation_status": status,
        "reference_matched": result.reference_matched,
        "reference_id": result.reference_id,
    }


def _presigned_get(key: str) -> str:
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": DOCUMENTS_BUCKET, "Key": key},
        ExpiresIn=300,
    )


def _hydrate(row: dict) -> dict:
    row = from_ddb(row)
    key = row.get("source_document_key")
    if key:
        row["document_url"] = _presigned_get(key)
    row["official_portal"] = lookup_portal(row.get("state"))
    return row


# ---- Route handlers -------------------------------------------------------

def _list_records(event: dict, request_id: str) -> dict:
    status = get_query_param(event, "status")
    limit = int(get_query_param(event, "limit", "25") or 25)
    limit = max(1, min(limit, 100))
    table = _dynamodb.Table(RECORDS_TABLE)
    if status:
        resp = table.query(
            IndexName="GSI3",
            KeyConditionExpression=Key("validation_status").eq(status),
            Limit=limit,
            ScanIndexForward=False,
        )
    else:
        resp = table.scan(Limit=limit)
    items = [from_ddb(i) for i in resp.get("Items", [])]
    return ok({"items": items})


def _get_record(event: dict, record_id: str, request_id: str) -> dict:
    table = _dynamodb.Table(RECORDS_TABLE)
    r = table.get_item(Key={"record_id": record_id})
    item = r.get("Item")
    if not item:
        return err("NOT_FOUND", f"record {record_id} not found", 404, request_id)
    return ok(_hydrate(item))


def _put_record(event: dict, record_id: str, request_id: str) -> dict:
    body = get_body(event)
    changes = {k: v for k, v in body.items() if k in EDITABLE_FIELDS}
    if not changes:
        return err("INVALID_REQUEST", "No editable fields in body", 400, request_id)

    user = get_caller_identity(event)
    table = _dynamodb.Table(RECORDS_TABLE)
    existing = table.get_item(Key={"record_id": record_id}).get("Item")
    if not existing:
        return err("NOT_FOUND", f"record {record_id} not found", 404, request_id)

    # Audit per-field
    for field, new_val in changes.items():
        old_val = existing.get(field)
        if str(old_val) != str(new_val):
            write_audit(
                record_id=record_id,
                action="HUMAN_CORRECTION",
                user=user,
                field=field,
                old_value=old_val,
                new_value=new_val,
            )

    merged = apply_correction(record_id, changes, user)
    reval = _revalidate(merged)
    # After a human correction that clears all HIGH flags → HUMAN_APPROVED.
    # If the reviewer's edits leave HIGH flags, keep NEEDS_REVIEW.
    has_high = any(f.get("severity") == "HIGH" for f in reval["validation_flags"])
    reval["validation_status"] = (
        "NEEDS_REVIEW" if has_high else STATUS_HUMAN_APPROVED
    )

    merged.update(reval)
    from backend.shared.dynamo import to_ddb
    table.put_item(Item=to_ddb(merged))

    write_audit(
        record_id=record_id,
        action="SYSTEM_REVALIDATE",
        user="system",
        note=f"status={reval['validation_status']} confidence={reval['overall_confidence']:.2f}",
    )

    return ok(_hydrate(merged))


def _approve(event: dict, record_id: str, request_id: str) -> dict:
    body = get_body(event)
    note = body.get("note", "")
    user = get_caller_identity(event)
    table = _dynamodb.Table(RECORDS_TABLE)
    existing = table.get_item(Key={"record_id": record_id}).get("Item")
    if not existing:
        return err("NOT_FOUND", f"record {record_id} not found", 404, request_id)
    from backend.shared.dynamo import to_ddb
    existing["validation_status"] = STATUS_HUMAN_APPROVED
    table.put_item(Item=to_ddb(existing))
    write_audit(record_id=record_id, action="HUMAN_APPROVED", user=user, note=note)
    return ok(_hydrate(existing))


def _reject(event: dict, record_id: str, request_id: str) -> dict:
    body = get_body(event)
    reason = body.get("reason", "")
    user = get_caller_identity(event)
    table = _dynamodb.Table(RECORDS_TABLE)
    existing = table.get_item(Key={"record_id": record_id}).get("Item")
    if not existing:
        return err("NOT_FOUND", f"record {record_id} not found", 404, request_id)
    from backend.shared.dynamo import to_ddb
    existing["validation_status"] = STATUS_REJECTED
    table.put_item(Item=to_ddb(existing))
    write_audit(record_id=record_id, action="REJECTED", user=user, note=reason)
    return ok(_hydrate(existing))


def _revalidate_only(event: dict, record_id: str, request_id: str) -> dict:
    table = _dynamodb.Table(RECORDS_TABLE)
    existing = table.get_item(Key={"record_id": record_id}).get("Item")
    if not existing:
        return err("NOT_FOUND", f"record {record_id} not found", 404, request_id)
    reval = _revalidate(existing)
    existing.update(reval)
    from backend.shared.dynamo import to_ddb
    table.put_item(Item=to_ddb(existing))
    write_audit(
        record_id=record_id,
        action="SYSTEM_REVALIDATE",
        user=get_caller_identity(event),
        note=f"status={reval['validation_status']} confidence={reval['overall_confidence']:.2f}",
    )
    return ok(_hydrate(existing))


# ---- Router ---------------------------------------------------------------

def handler(event: dict, _context) -> dict:
    request_id = (event.get("requestContext") or {}).get("requestId", "")
    method = event.get("httpMethod")
    path = event.get("resource") or event.get("path") or ""
    record_id = get_path_param(event, "id")

    try:
        if path.endswith("/records") and method == "GET":
            return _list_records(event, request_id)
        if path.endswith("/records/{id}") and method == "GET" and record_id:
            return _get_record(event, record_id, request_id)
        if path.endswith("/records/{id}") and method == "PUT" and record_id:
            return _put_record(event, record_id, request_id)
        if path.endswith("/approve") and method == "POST" and record_id:
            return _approve(event, record_id, request_id)
        if path.endswith("/reject") and method == "POST" and record_id:
            return _reject(event, record_id, request_id)
        if path.endswith("/revalidate") and method == "POST" and record_id:
            return _revalidate_only(event, record_id, request_id)
        return err("NOT_FOUND", f"No route for {method} {path}", 404, request_id)
    except Exception as e:
        logger.exception("records handler failed")
        return err("INTERNAL_ERROR", str(e), 500, request_id)
