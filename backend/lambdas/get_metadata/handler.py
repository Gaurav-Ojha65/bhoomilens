"""Step Functions state: GetMetadata.

Input from EventBridge target:
  { "bucket": ..., "key": "raw/<document_id>.<ext>", "size": ..., "eventTime": ... }

Output:
  { "record_id", "document_id", "bucket", "key", "content_type", "size" }

The record row was already created by the Upload Lambda in PENDING state.
We look it up by document_id via GSI1.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import unquote_plus

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")
_s3 = boto3.client("s3")

RECORDS_TABLE = os.environ["RECORDS_TABLE"]


def _document_id_from_key(key: str) -> str:
    # "raw/<uuid>.<ext>"
    base = key.split("/", 1)[1] if "/" in key else key
    return base.rsplit(".", 1)[0]


def handler(event: dict, _context) -> dict:
    bucket = event["bucket"]
    key = unquote_plus(event["key"])
    document_id = _document_id_from_key(key)

    table = _dynamodb.Table(RECORDS_TABLE)
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("document_id").eq(document_id),
        Limit=1,
    )
    items = resp.get("Items") or []
    if not items:
        # An upload happened without a PENDING row (e.g., direct console upload).
        # Create a minimal row so the pipeline can continue.
        from backend.shared.persistence import new_record_id, put_pending_record
        record_id = new_record_id()
        put_pending_record(
            record_id=record_id,
            document_id=document_id,
            source_document_key=key,
            uploaded_by="unknown",
        )
    else:
        record_id = items[0]["record_id"]

    head = _s3.head_object(Bucket=bucket, Key=key)

    output = {
        "record_id": record_id,
        "document_id": document_id,
        "bucket": bucket,
        "key": key,
        "content_type": head.get("ContentType", "application/octet-stream"),
        "size": head.get("ContentLength", 0),
    }
    logger.info("GetMetadata output: %s", output)
    return output
