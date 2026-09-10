"""Final Step Functions state: persist the processed record + write an audit row."""

from __future__ import annotations

import logging

from backend.shared.persistence import upsert_processed_record, write_audit

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, _context) -> dict:
    validation = event.get("validation") or {}
    processed = {
        "record_id": validation.get("record_id") or event.get("record_id"),
        "document_id": validation.get("document_id") or event.get("document_id"),
        "validation_status": validation.get("validation_status", "NEEDS_REVIEW"),
        "overall_confidence": validation.get("overall_confidence", 0.0),
        "validation_score": validation.get("validation_score", 0.0),
        "validation_flags": validation.get("validation_flags", []),
        "reference_matched": validation.get("reference_matched", False),
        "reference_id": validation.get("reference_id"),
        "extracted": validation.get("extracted", {}),
        "ocr_confidence": validation.get("ocr_confidence"),
        "extraction_confidence": validation.get("extraction_confidence"),
    }

    row = upsert_processed_record(processed)

    write_audit(
        record_id=processed["record_id"],
        action="AUTO_INGEST",
        user="system",
        note=(
            f"status={processed['validation_status']} "
            f"confidence={processed['overall_confidence']:.2f} "
            f"flags={len(processed['validation_flags'])}"
        ),
    )
    logger.info("Persisted record_id=%s status=%s", row["record_id"], row["validation_status"])
    return {"record_id": row["record_id"], "validation_status": row["validation_status"]}
