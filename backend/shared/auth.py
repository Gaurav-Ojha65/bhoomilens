"""Authentication and role helpers for API Gateway + Cognito."""

from __future__ import annotations

import os
from typing import Any

from backend.shared.http import err

ROLE_USER = "USER"
ROLE_SUPERVISOR = "SUPERVISOR"


def get_caller_claims(event: dict) -> dict[str, Any]:
    return (
        ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims")
        or {}
    )


def get_caller_identity(event: dict) -> str:
    claims = get_caller_claims(event)
    return claims.get("email") or claims.get("sub") or "unknown"


def get_caller_groups(event: dict) -> set[str]:
    raw = get_caller_claims(event).get("cognito:groups") or ""
    if isinstance(raw, list):
        return {str(group).strip().upper() for group in raw if str(group).strip()}
    return {
        group.strip().upper()
        for group in str(raw).replace(";", ",").split(",")
        if group.strip()
    }


def _configured_supervisors() -> set[str]:
    raw = os.environ.get("SUPERVISOR_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def get_caller_role(event: dict) -> str:
    groups = get_caller_groups(event)
    if ROLE_SUPERVISOR in groups:
        return ROLE_SUPERVISOR

    # Deployment-time allowlist is a fallback for environments where the
    # Cognito groups cannot yet be populated by the team. The value is
    # server-side configuration; the browser cannot choose its own role.
    identity = get_caller_identity(event).lower()
    if identity in _configured_supervisors():
        return ROLE_SUPERVISOR

    return ROLE_USER


def is_supervisor(event: dict) -> bool:
    return get_caller_role(event) == ROLE_SUPERVISOR


def require_supervisor(event: dict, request_id: str | None = None) -> dict | None:
    if is_supervisor(event):
        return None
    return err(
        "FORBIDDEN",
        "Supervisor access is required for this operation",
        403,
        request_id,
    )
