"""GET /review-queue — records that need a human."""

from __future__ import annotations

import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

from backend.shared.dynamo import from_ddb
from backend.shared.http import ok

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")
RECORDS_TABLE = os.environ["RECORDS_TABLE"]


def handler(event: dict, _context) -> dict:
    table = _dynamodb.Table(RECORDS_TABLE)
    items = []
    for status in ("NEEDS_REVIEW", "HIGH_RISK"):
        resp = table.query(
            IndexName="GSI3",
            KeyConditionExpression=Key("validation_status").eq(status),
            Limit=50,
            ScanIndexForward=True,  # oldest first
        )
        items.extend(resp.get("Items", []))
    items.sort(key=lambda r: r.get("updated_at", ""))
    return ok({"items": [from_ddb(i) for i in items]})
