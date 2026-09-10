"""POST /documents/upload

Creates a PENDING record row and returns a presigned S3 PUT URL.
The browser PUTs the file directly to S3, which fires the pipeline.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import boto3
from botocore.config import Config

from backend.shared.http import err, get_body, get_caller_identity, ok
from backend.shared.persistence import (
    new_document_id,
    new_record_id,
    put_pending_record,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3", config=Config(signature_version="s3v4"))

BUCKET = os.environ["DOCUMENTS_BUCKET"]
MAX_BYTES = 20 * 1024 * 1024  # 20 MB

_ALLOWED_MIME = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}


def _extension(content_type: str) -> Optional[str]:
    return _ALLOWED_MIME.get(content_type.lower())


def handler(event: dict, _context) -> dict:
    request_id = (event.get("requestContext") or {}).get("requestId")
    body = get_body(event)

    filename = (body.get("filename") or "").strip()
    content_type = (body.get("content_type") or "").strip()
    size = body.get("size_bytes")

    if not filename:
        return err("INVALID_REQUEST", "filename is required", 400, request_id)
    ext = _extension(content_type)
    if not ext:
        return err(
            "UNSUPPORTED_MEDIA_TYPE",
            f"content_type must be one of {sorted(_ALLOWED_MIME.keys())}",
            415, request_id,
        )
    if not isinstance(size, int) or size <= 0 or size > MAX_BYTES:
        return err(
            "PAYLOAD_TOO_LARGE",
            f"size_bytes must be a positive integer <= {MAX_BYTES}",
            413, request_id,
        )

    document_id = new_document_id()
    record_id = new_record_id()
    key = f"raw/{document_id}.{ext}"
    caller = get_caller_identity(event)

    try:
        put_pending_record(
            record_id=record_id,
            document_id=document_id,
            source_document_key=key,
            uploaded_by=caller,
        )
    except Exception:
        logger.exception("Failed to write PENDING record")
        return err("INTERNAL_ERROR", "Could not create pending record", 500, request_id)

    try:
        upload_url = _s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET,
                "Key": key,
                "ContentType": content_type,
                # Tag original filename in object metadata for the reviewer UI
                "Metadata": {"original-filename": filename},
            },
            ExpiresIn=300,
            HttpMethod="PUT",
        )
    except Exception:
        logger.exception("Presign failed")
        return err("INTERNAL_ERROR", "Could not generate upload URL", 500, request_id)

    logger.info(
        "Prepared upload record_id=%s document_id=%s size=%d by=%s",
        record_id, document_id, size, caller,
    )
    return ok({
        "document_id": document_id,
        "record_id": record_id,
        "upload_url": upload_url,
        "expires_in": 300,
    })
