"""State → official land-record portal mapping.

Loaded from data/state_portals.json at module import time. The JSON file
is packaged into the Lambda deployment bundle (see infrastructure).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _find_portals_file() -> Path:
    """The file might live at different relative paths in Lambda vs local dev."""
    override = os.environ.get("STATE_PORTALS_FILE")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "data" / "state_portals.json",  # repo root
        Path("/var/task/data/state_portals.json"),                  # Lambda
        here.parent.parent / "data" / "state_portals.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fall back to a bundled copy if the real one isn't found.
    return here.parent / "state_portals.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    p = _find_portals_file()
    if not p.exists():
        return {"portals": {}}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _norm_key(state: str) -> str:
    return state.strip().lower()


def lookup_portal(state: Optional[str]) -> dict:
    """Return {label, url, cadastral_map_url} for the given state (or the default)."""
    data = _load().get("portals", {})
    if state:
        entry = data.get(_norm_key(state))
        if entry:
            return {
                "state": state,
                "label": entry.get("label"),
                "url": entry.get("url"),
                "cadastral_map_url": entry.get("cadastral_map_url"),
                "notes": entry.get("notes", ""),
            }
    default = data.get("_default") or {}
    return {
        "state": state,
        "label": default.get("label", "National land-records portal"),
        "url": default.get("url"),
        "cadastral_map_url": default.get("cadastral_map_url"),
        "notes": default.get("notes", ""),
    }
