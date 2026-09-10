# BhoomiLens — API Reference

All endpoints are behind API Gateway with a Cognito authorizer. The client sends `Authorization: Bearer <id_token>` on every request. CORS is restricted to the Amplify domain.

Base URL: `${API_ENDPOINT}` (from `.env` after `cdk deploy`).

---

## `POST /documents/upload`

Request an S3 presigned PUT URL for a new document.

**Request body:**
```json
{
  "filename": "old_khasra_rampur.pdf",
  "content_type": "application/pdf",
  "size_bytes": 1245678
}
```

**Response 200:**
```json
{
  "document_id": "9b5c...",
  "record_id": "01HXY...",
  "upload_url": "https://s3.ap-south-1.amazonaws.com/bhoomilens-documents-.../raw/9b5c....pdf?...",
  "expires_in": 300
}
```

**Errors:**
- `400` — invalid mime type or size > 20MB
- `401` — missing/invalid token

Client then does a `PUT` to `upload_url` with the file body. S3 fires an `ObjectCreated` event → EventBridge → Step Functions.

---

## `GET /records`

List records with filtering.

**Query params:**
- `status` — one of `PENDING`, `AUTO_APPROVED`, `NEEDS_REVIEW`, `HIGH_RISK`, `HUMAN_APPROVED`, `REJECTED`
- `owner` — substring of `owner_name_norm`
- `khasra` — exact match on `khasra_number`
- `village` — exact match
- `min_confidence` / `max_confidence` — integer 0..100
- `issue_type` — filter records that have this flag
- `limit` — 1..100 (default 25)
- `cursor` — opaque pagination cursor

**Response 200:**
```json
{
  "items": [{ /* record */ }],
  "next_cursor": "eyJwayI6..."
}
```

---

## `GET /records/{id}`

Full record + a presigned GET URL for the original document (5-minute expiry).

**Response 200:** the `records` row plus:
```json
{
  "document_url": "https://s3.../raw/...?...",
  "document_content_type": "application/pdf",
  "official_portal": {
    "state": "Uttar Pradesh",
    "url": "https://upbhulekh.gov.in/",
    "label": "UP Bhulekh"
  }
}
```

---

## `GET /review-queue`

Shorthand for `GET /records?status=NEEDS_REVIEW&status=HIGH_RISK` ordered by oldest `updated_at`.

---

## `PUT /records/{id}`

Update fields. Triggers a **synchronous** revalidation.

**Request body:** any subset of editable fields:
```json
{
  "owner_name": "Ram Prasad",
  "khasra_number": "117/2",
  "area": 2.5,
  "area_unit": "hectare",
  "village": "Rampur",
  "khata_number": "284"
}
```

**Response 200:** the updated record with new `validation_flags`, `overall_confidence`, `validation_status`. An `audit` row is written per changed field.

**Errors:**
- `400` — schema violation
- `409` — the record was updated by someone else since your GET (uses `If-Match: <etag>` header when supplied)

---

## `POST /records/{id}/approve`

Reviewer stamps a `NEEDS_REVIEW` record as approved.

**Request body:**
```json
{ "note": "Verified against UP Bhulekh manually." }
```

**Response 200:** record with `validation_status = HUMAN_APPROVED`. Writes an `audit` row with `action = HUMAN_APPROVED` and the note.

---

## `POST /records/{id}/reject`

**Request body:**
```json
{ "reason": "Document appears altered — sending back to citizen." }
```

**Response 200:** record with `validation_status = REJECTED`. Audit row written.

---

## `POST /records/{id}/revalidate`

Re-run validation without changing fields (e.g., after the reference registry is updated).

**Response 200:** updated record.

---

## `GET /records/{id}/audit`

Full audit history for a record, newest first.

**Response 200:**
```json
{
  "items": [
    {
      "record_id": "01HXY...",
      "timestamp": "2026-09-10T14:22:03.123Z",
      "action": "HUMAN_CORRECTION",
      "field": "area",
      "old_value": "5.2",
      "new_value": "2.5",
      "user": "reviewer@example.com"
    }
  ]
}
```

---

## `GET /dashboard/metrics`

**Response 200:**
```json
{
  "total_documents": 128,
  "auto_approved": 96,
  "needs_review": 32,
  "high_risk": 4,
  "average_extraction_confidence": 0.942,
  "validation_issues": {
    "AREA_MISMATCH": 18,
    "OWNER_MISMATCH": 7,
    "DUPLICATE_KHASRA": 12,
    "MISSING_REQUIRED_FIELD": 21
  },
  "generated_at": "2026-09-10T14:22:03Z"
}
```

Backed by a bounded DynamoDB scan (max 5000 items) plus in-memory aggregation. For production, this would become a materialized counter table updated by DynamoDB streams — out of scope for the hackathon.

---

## Error format

All errors:
```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "size_bytes must be <= 20971520",
    "request_id": "abc-123"
  }
}
```

`request_id` echoes the API Gateway request ID for CloudWatch correlation.
