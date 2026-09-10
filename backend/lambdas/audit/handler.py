"""GET /records/{id}/audit — audit trail, newest first."""

from __future__ import annotations

import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

from backend.shared.dynamo import from_ddb
from backend.shared.http import err, get_path_param, ok

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")
AUDIT_TABLE = os.environ["AUDIT_TABLE"]


def handler(event: dict, _context) -> dict:
    request_id = (event.get("requestContext") or {}).get("requestId", "")
    record_id = get_path_param(event, "id")
    if not record_id:
        return err("INVALID_REQUEST", "record id path parameter is required", 400, request_id)

    table = _dynamodb.Table(AUDIT_TABLE)
    resp = table.query(
        KeyConditionExpression=Key("record_id").eq(record_id),
        ScanIndexForward=False,
        Limit=200,
    )
    return ok({"items": [from_ddb(i) for i in resp.get("Items", [])]})
