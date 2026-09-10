"""GET /dashboard/metrics — real numbers from a bounded scan.

Not a materialized counter for the MVP. For production, DynamoDB Streams
+ an aggregate table is the right pattern.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timezone

import boto3

from backend.shared.dynamo import from_ddb
from backend.shared.http import ok

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")
RECORDS_TABLE = os.environ["RECORDS_TABLE"]

MAX_ITEMS = 5000


def handler(event: dict, _context) -> dict:
    table = _dynamodb.Table(RECORDS_TABLE)
    total = 0
    by_status: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    extraction_sum = 0.0
    extraction_n = 0

    last_key = None
    while total < MAX_ITEMS:
        kwargs = {"Limit": min(500, MAX_ITEMS - total)}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = table.scan(**kwargs)
        for row in resp.get("Items", []):
            total += 1
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
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break

    avg_extraction = extraction_sum / extraction_n if extraction_n else 0.0

    return ok(from_ddb({
        "total_documents": total,
        "auto_approved": by_status.get("AUTO_APPROVED", 0),
        "human_approved": by_status.get("HUMAN_APPROVED", 0),
        "needs_review": by_status.get("NEEDS_REVIEW", 0),
        "high_risk": by_status.get("HIGH_RISK", 0),
        "pending": by_status.get("PENDING", 0),
        "rejected": by_status.get("REJECTED", 0),
        "average_extraction_confidence": round(avg_extraction, 4),
        "validation_issues": dict(flag_counts),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_limited_to": MAX_ITEMS,
    }))
