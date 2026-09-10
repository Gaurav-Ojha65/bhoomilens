"""OCR Lambda handler.

Input (from Step Functions GetMetadata):
  { "record_id", "document_id", "bucket", "key", "content_type", "size" }

Output:
  {
    "text": "concatenated line-by-line text",
    "pages": [ { "page_no": 1, "text": "...", "avg_confidence": 0.92 } ],
    "blocks": [ { "bbox": [...], "text": "...", "confidence": 0.87, "page": 1 } ],
    "language": "hi" | "en" | "mixed" | "unknown",
    "ocr_confidence": 0.0..1.0
  }

Language autodetection is best-effort: Hindi vs English is decided by
Devanagari codepoint ratio in the recognized text.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")

# PaddleOCR gets instantiated lazily so cold-start still passes the SFN
# retry once the model files are downloaded (~40MB).
_ocr_hi = None
_ocr_en = None


def _get_ocr(lang: str):
    from paddleocr import PaddleOCR
    global _ocr_hi, _ocr_en
    if lang == "hi":
        if _ocr_hi is None:
            _ocr_hi = PaddleOCR(use_angle_cls=True, lang="hi", show_log=False)
        return _ocr_hi
    if _ocr_en is None:
        _ocr_en = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _ocr_en


def _download_document(bucket: str, key: str) -> bytes:
    buf = io.BytesIO()
    _s3.download_fileobj(bucket, key, buf)
    return buf.getvalue()


def _pdf_to_images(pdf_bytes: bytes) -> list:
    from pdf2image import convert_from_bytes
    return convert_from_bytes(pdf_bytes, dpi=300, fmt="png")


def _image_to_ndarray(pil_img):
    import numpy as np
    return np.array(pil_img.convert("RGB"))


def _detect_language(sample_text: str) -> str:
    if not sample_text:
        return "unknown"
    dev = sum(1 for ch in sample_text if "ऀ" <= ch <= "ॿ")
    latin = sum(1 for ch in sample_text if ("a" <= ch.lower() <= "z"))
    if dev == 0 and latin == 0:
        return "unknown"
    ratio = dev / max(dev + latin, 1)
    if ratio > 0.7:
        return "hi"
    if ratio < 0.15:
        return "en"
    return "mixed"


def _run_ocr_on_image(np_img, lang: str) -> list:
    ocr = _get_ocr(lang)
    return ocr.ocr(np_img, cls=True)


def _flatten_paddle_output(paddle_output: list, page_no: int) -> tuple[list, str, float]:
    """PaddleOCR output shape: [ [ [bbox, (text, conf)], ... ] ] per image."""
    blocks = []
    all_confs = []
    lines = []
    if not paddle_output or paddle_output[0] is None:
        return blocks, "", 0.0
    for line in paddle_output[0]:
        bbox, (text, conf) = line[0], line[1]
        blocks.append({
            "bbox": [[float(x), float(y)] for x, y in bbox],
            "text": text,
            "confidence": float(conf),
            "page": page_no,
        })
        all_confs.append(float(conf))
        lines.append(text)
    avg = sum(all_confs) / len(all_confs) if all_confs else 0.0
    return blocks, "\n".join(lines), avg


def handler(event: dict, _context) -> dict:
    bucket = event["bucket"]
    key = event["key"]
    content_type = (event.get("content_type") or "").lower()

    doc_bytes = _download_document(bucket, key)

    if content_type == "application/pdf" or key.lower().endswith(".pdf"):
        pil_pages = _pdf_to_images(doc_bytes)
    else:
        from PIL import Image
        pil_pages = [Image.open(io.BytesIO(doc_bytes))]

    all_blocks: list[dict[str, Any]] = []
    per_page: list[dict[str, Any]] = []
    confidences: list[float] = []
    combined_text = []

    # Pass 1: Hindi model. Pass 2 (only if Hindi text looks scarce): English.
    for i, pil in enumerate(pil_pages, start=1):
        np_img = _image_to_ndarray(pil)
        paddle_out_hi = _run_ocr_on_image(np_img, "hi")
        blocks_hi, text_hi, avg_hi = _flatten_paddle_output(paddle_out_hi, i)
        # If Hindi produced little text, run English too and keep the higher-confidence one.
        if avg_hi < 0.55 or len(text_hi.strip()) < 20:
            paddle_out_en = _run_ocr_on_image(np_img, "en")
            blocks_en, text_en, avg_en = _flatten_paddle_output(paddle_out_en, i)
            if avg_en > avg_hi:
                blocks_page, text_page, avg_page = blocks_en, text_en, avg_en
            else:
                blocks_page, text_page, avg_page = blocks_hi, text_hi, avg_hi
        else:
            blocks_page, text_page, avg_page = blocks_hi, text_hi, avg_hi

        all_blocks.extend(blocks_page)
        per_page.append({"page_no": i, "text": text_page, "avg_confidence": avg_page})
        confidences.append(avg_page)
        combined_text.append(text_page)

    text = "\n\n".join(combined_text).strip()
    language = _detect_language(text)
    ocr_conf = sum(confidences) / len(confidences) if confidences else 0.0

    logger.info(
        "OCR done record_id=%s pages=%d chars=%d lang=%s conf=%.2f",
        event.get("record_id"), len(per_page), len(text), language, ocr_conf,
    )

    return {
        "text": text,
        "pages": per_page,
        "blocks": all_blocks[:200],  # cap payload size going back to SFN
        "language": language,
        "ocr_confidence": round(ocr_conf, 4),
    }
