"""Tiny HTTP helpers for API Gateway proxy Lambdas.

Keeps every handler's response shape consistent.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Optional

from .dynamo import _DecimalEncoder


_ALLOWED_ORIGIN = os.environ.get("CORS_ALLOWED_ORIGIN", "*")


def _cors_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": _ALLOWED_ORIGIN,
        "Access-Control-Allow-Headers":
            "Content-Type, Authorization, X-Amz-Date, X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    }


def ok(body: Any, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": _cors_headers(),
        "body": json.dumps(body, cls=_DecimalEncoder, default=str),
    }


def err(code: str, message: str, status: int = 400, request_id: Optional[str] = None) -> dict:
    return {
        "statusCode": status,
        "headers": _cors_headers(),
        "body": json.dumps({
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id or str(uuid.uuid4()),
            }
        }),
    }


def get_body(event: dict) -> dict:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")
    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {}


def get_path_param(event: dict, name: str) -> Optional[str]:
    return (event.get("pathParameters") or {}).get(name)


def get_query_param(event: dict, name: str, default: Optional[str] = None) -> Optional[str]:
    return (event.get("queryStringParameters") or {}).get(name, default)


def get_caller_identity(event: dict) -> str:
    """Extract the reviewer's identity from Cognito authorizer claims."""
    claims = (
        (event.get("requestContext") or {})
        .get("authorizer", {})
        .get("claims")
        or {}
    )
    return claims.get("email") or claims.get("sub") or "unknown"
