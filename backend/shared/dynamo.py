"""Small DynamoDB helpers — Decimal <-> float bridging + type coercion.

DynamoDB's Python SDK insists on Decimal for numbers. Our API contract is
JSON — floats/ints. These helpers translate at the boundary.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            if o % 1 == 0:
                return int(o)
            return float(o)
        return super().default(o)


def to_json(obj: Any) -> str:
    return json.dumps(obj, cls=_DecimalEncoder, default=str)


def from_ddb(item: Any) -> Any:
    """Recursively convert DynamoDB Decimal to Python int/float."""
    if isinstance(item, list):
        return [from_ddb(v) for v in item]
    if isinstance(item, dict):
        return {k: from_ddb(v) for k, v in item.items()}
    if isinstance(item, Decimal):
        if item % 1 == 0:
            return int(item)
        return float(item)
    return item


def to_ddb(value: Any) -> Any:
    """Convert Python floats to Decimal so boto3 stops complaining.

    ints and strings pass through. NaN/inf become None (DynamoDB refuses them).
    """
    if isinstance(value, list):
        return [to_ddb(v) for v in value]
    if isinstance(value, dict):
        return {k: to_ddb(v) for k, v in value.items()}
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return Decimal(str(value))
    return value
