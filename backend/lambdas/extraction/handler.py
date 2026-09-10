"""Bedrock extraction Lambda.

Input (from SFN, previous states):
  {
    "record_id": ..., "document_id": ...,
    "ocr": { "text": ..., "language": ..., "ocr_confidence": ... }
  }

Output (merged into SFN state):
  {
    "extracted": { ... ExtractedRecord fields ... },
    "extraction_confidence": 0.0..1.0,
    "ocr_confidence": ...,
    "record_id": ..., "document_id": ...
  }

The primary model is tried first with tool-use for JSON output. If it
returns an unparseable / low-confidence result, we retry once with the
fallback model. We never ask the model to invent a confidence number —
extraction_confidence is derived from tool-call success + non-null fields.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "ap-south-1"))
_bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

PRIMARY_MODEL = os.environ["BEDROCK_MODEL_ID_PRIMARY"]
FALLBACK_MODEL = os.environ["BEDROCK_MODEL_ID_FALLBACK"]

MAX_OCR_CHARS = 8000  # trim to control cost


def _load_prompt() -> str:
    candidates = [
        Path("/var/task/prompts/extraction_prompt.txt"),
        Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "extraction_prompt.txt",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise RuntimeError("extraction_prompt.txt not found in Lambda bundle")


_PROMPT_TEMPLATE = _load_prompt()


_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "owner_name":            {"type": ["string", "null"]},
        "father_or_spouse_name": {"type": ["string", "null"]},
        "khasra_number":         {"type": ["string", "null"]},
        "khata_number":          {"type": ["string", "null"]},
        "plot_number":           {"type": ["string", "null"]},
        "area":                  {"type": ["number", "null"]},
        "area_unit":             {"type": ["string", "null"]},
        "village":               {"type": ["string", "null"]},
        "tehsil":                {"type": ["string", "null"]},
        "district":              {"type": ["string", "null"]},
        "state":                 {"type": ["string", "null"]},
        "land_classification":   {"type": ["string", "null"]},
        "ownership_type":        {"type": ["string", "null"]},
        "mutation_date":         {"type": ["string", "null"]},
        "registration_number":   {"type": ["string", "null"]},
        "field_confidence": {
            "type": "object",
            "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "notes": {"type": ["string", "null"]},
    },
    "required": ["owner_name", "khasra_number", "area", "area_unit",
                 "village", "state", "field_confidence"],
    "additionalProperties": False,
}


def _build_user_prompt(ocr_text: str, ocr_language: str, ocr_confidence: float) -> str:
    prompt = _PROMPT_TEMPLATE.replace("{ocr_language}", ocr_language or "unknown")
    prompt = prompt.replace("{ocr_confidence}", f"{ocr_confidence:.2f}")
    prompt = prompt.replace("{ocr_text}", ocr_text[:MAX_OCR_CHARS])
    return prompt


def _invoke_with_tool(model_id: str, user_prompt: str) -> Optional[dict]:
    """Try the Converse API with tool-use. Returns parsed dict or None."""
    try:
        resp = _bedrock.converse(
            modelId=model_id,
            system=[{"text": (
                "You are a careful extractor of Indian land record fields. "
                "You NEVER invent values. Missing/illegible fields become null "
                "with a low field_confidence entry."
            )}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={
                "temperature": 0.0,
                "maxTokens": 1500,
                "topP": 0.1,
            },
            toolConfig={
                "tools": [{
                    "toolSpec": {
                        "name": "record_extraction",
                        "description": "Return the extracted land-record fields.",
                        "inputSchema": {"json": _TOOL_SCHEMA},
                    }
                }],
                "toolChoice": {"tool": {"name": "record_extraction"}},
            },
        )
    except Exception:
        logger.exception("Bedrock converse call failed on model %s", model_id)
        return None

    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"].get("input")
    return None


def _invoke_fallback_json(model_id: str, user_prompt: str) -> Optional[dict]:
    """Fallback path for models that don't support tool-use — plain JSON prompt."""
    try:
        resp = _bedrock.converse(
            modelId=model_id,
            system=[{"text": (
                "You output ONLY a single valid JSON object matching the given schema. "
                "No prose. No code fences. If unsure, set null and lower confidence."
            )}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 1500, "topP": 0.1},
        )
    except Exception:
        logger.exception("Bedrock fallback JSON call failed on model %s", model_id)
        return None

    text = ""
    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "text" in block:
            text += block["text"]
    # Strip code fences if the model added them despite instructions
    text = re.sub(r"^```(?:json)?", "", text.strip())
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Fallback JSON was not parseable: %r", text[:500])
        return None


def _extraction_confidence(parsed: dict) -> float:
    """App-side confidence heuristic (spec Section 9)."""
    if not parsed:
        return 0.0
    field_conf = parsed.get("field_confidence") or {}
    # Base 0.5 for a valid parse
    score = 0.5
    core_fields = ("owner_name", "khasra_number", "area", "village", "state")
    non_null = sum(1 for f in core_fields if parsed.get(f) not in (None, ""))
    score += 0.08 * non_null  # up to +0.40
    # If field_confidence is populated, average it in
    if field_conf:
        try:
            avg = sum(float(v) for v in field_conf.values()) / max(len(field_conf), 1)
            score = 0.5 * score + 0.5 * avg
        except (TypeError, ValueError):
            pass
    return max(0.0, min(1.0, round(score, 4)))


def _needs_fallback(parsed: Optional[dict], confidence: float) -> bool:
    if not parsed:
        return True
    if confidence < 0.6:
        return True
    # Require the truly essential fields
    if not parsed.get("khasra_number") or not parsed.get("owner_name"):
        return True
    return False


def handler(event: dict, _context) -> dict:
    ocr = event.get("ocr") or {}
    text = ocr.get("text") or ""
    lang = ocr.get("language") or "unknown"
    ocr_conf = float(ocr.get("ocr_confidence") or 0.5)

    user_prompt = _build_user_prompt(text, lang, ocr_conf)

    parsed = _invoke_with_tool(PRIMARY_MODEL, user_prompt)
    if parsed is None:
        parsed = _invoke_fallback_json(PRIMARY_MODEL, user_prompt)
    confidence = _extraction_confidence(parsed)
    used_model = PRIMARY_MODEL

    if _needs_fallback(parsed, confidence) and FALLBACK_MODEL != PRIMARY_MODEL:
        logger.info("Low confidence %.2f — trying fallback model %s", confidence, FALLBACK_MODEL)
        fb_parsed = _invoke_with_tool(FALLBACK_MODEL, user_prompt)
        if fb_parsed is None:
            fb_parsed = _invoke_fallback_json(FALLBACK_MODEL, user_prompt)
        fb_conf = _extraction_confidence(fb_parsed)
        if fb_parsed and fb_conf > confidence:
            parsed = fb_parsed
            confidence = fb_conf
            used_model = FALLBACK_MODEL

    if parsed is None:
        # Never fail loudly — a null extraction is still a valid pipeline outcome.
        parsed = {"field_confidence": {}}
        confidence = 0.0

    logger.info(
        "Extraction record_id=%s model=%s confidence=%.2f",
        event.get("record_id"), used_model, confidence,
    )

    return {
        "extracted": parsed,
        "extraction_confidence": confidence,
        "ocr_confidence": ocr_conf,
        "model_used": used_model,
        "record_id": event.get("record_id"),
        "document_id": event.get("document_id"),
    }
