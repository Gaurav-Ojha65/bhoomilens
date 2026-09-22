"""Dashboard and supervisor aggregation endpoints."""

from __future__ import annotations

import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone

import boto3

from backend.shared.auth import require_supervisor
from backend.shared.dynamo import from_ddb
from backend.shared.http import err, get_caller_identity, ok

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")
RECORDS_TABLE = os.environ["RECORDS_TABLE"]

MAX_ITEMS = 5000


def _scan_records():
    table = _dynamodb.Table(RECORDS_TABLE)
    rows = []
    last_key = None
    while len(rows) < MAX_ITEMS:
        kwargs = {"Limit": min(500, MAX_ITEMS - len(rows))}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = table.scan(**kwargs)
        rows.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return rows[:MAX_ITEMS]


def _metrics(rows: list[dict]) -> dict:
    by_status: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    extraction_sum = 0.0
    extraction_n = 0

    for row in rows:
        by_status[row.get("validation_status", "UNKNOWN")] += 1
        for flag in row.get("validation_flags", []) or []:
            if isinstance(flag, dict) and flag.get("issue_type"):
                flag_counts[flag["issue_type"]] += 1
        conf = row.get("extraction_confidence")
        if conf is not None:
            try:
                extraction_sum += float(conf)
                extraction_n += 1
            except (TypeError, ValueError):
                pass

    return {
        "total_documents": len(rows),
        "auto_approved": by_status.get("AUTO_APPROVED", 0),
        "human_approved": by_status.get("HUMAN_APPROVED", 0),
        "needs_review": by_status.get("NEEDS_REVIEW", 0),
        "high_risk": by_status.get("HIGH_RISK", 0),
        "pending": by_status.get("PENDING", 0),
        "rejected": by_status.get("REJECTED", 0),
        "average_extraction_confidence": round(
            extraction_sum / extraction_n if extraction_n else 0.0, 4
        ),
        "validation_issues": dict(flag_counts),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_limited_to": MAX_ITEMS,
    }


def _supervisor_users(rows: list[dict]) -> list[dict]:
    users: dict[str, dict] = defaultdict(
        lambda: {"email": "", "records": 0, "last_activity": None, "statuses": Counter()}
    )
    for raw in rows:
        row = from_ddb(raw)
        identity = str(row.get("uploaded_by") or "").strip()
        if not identity or identity == "unknown":
            continue
        item = users[identity]
        item["email"] = identity
        item["records"] += 1
        item["statuses"][row.get("validation_status", "UNKNOWN")] += 1
        updated = row.get("updated_at") or row.get("created_at")
        if updated and (item["last_activity"] is None or updated > item["last_activity"]):
            item["last_activity"] = updated

    result = []
    for item in users.values():
        statuses = dict(item["statuses"])
        result.append({
            "email": item["email"],
            "records": item["records"],
            "last_activity": item["last_activity"],
            "needs_review": statuses.get("NEEDS_REVIEW", 0),
            "high_risk": statuses.get("HIGH_RISK", 0),
            "approved": statuses.get("AUTO_APPROVED", 0) + statuses.get("HUMAN_APPROVED", 0),
            "rejected": statuses.get("REJECTED", 0),
        })
    return sorted(result, key=lambda x: (x["last_activity"] or ""), reverse=True)


def handler(event: dict, _context) -> dict:
    request_id = (event.get("requestContext") or {}).get("requestId", "")
    path = event.get("resource") or event.get("path") or ""

    if path.endswith("/supervisor/users"):
        denied = require_supervisor(event, request_id)
        if denied:
            return denied
        return ok({
            "items": _supervisor_users(_scan_records()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scan_limited_to": MAX_ITEMS,
        })

    return ok(_metrics(_scan_records()))
