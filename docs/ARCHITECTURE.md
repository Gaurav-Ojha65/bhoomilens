# BhoomiLens — Architecture

## 1. Guiding principles

1. **AWS is the backbone, not the hosting layer.** Every meaningful capability is an AWS-native service.
2. **Serverless-first.** Pay-per-use; no long-running compute unless the workload demands it.
3. **Event-driven, asynchronous.** S3 upload triggers a Step Functions workflow. The user does not wait for OCR on the HTTP request.
4. **Human review lives outside Step Functions.** No `waitForTaskToken` — the workflow ends at `AUTO_APPROVED` or `NEEDS_REVIEW`. Human review is a plain REST + DynamoDB operation.
5. **Deterministic validation is the differentiator.** LLMs extract; Python rules validate. The LLM never decides "consistent" or "authentic".
6. **Every layer is modular.** OCR, extraction model, reference source can each be swapped without touching the others.

---

## 2. Component diagram

```
                        ┌───────────────────────────────────────┐
                        │           User (browser)              │
                        └────────────────────┬──────────────────┘
                                             │
                                             ▼
                        ┌───────────────────────────────────────┐
                        │  AWS Amplify Hosting (Next.js SSR)    │
                        └────────────────────┬──────────────────┘
                                             │  JWT (Cognito)
                                             ▼
                        ┌───────────────────────────────────────┐
                        │        Amazon API Gateway (REST)      │
                        │  Cognito authorizer on every route    │
                        └───┬──────────────┬──────────────┬─────┘
                            │              │              │
                            ▼              ▼              ▼
                     ┌───────────┐  ┌───────────┐  ┌──────────────┐
                     │  Upload   │  │  Review   │  │   Dashboard  │
                     │  Lambda   │  │  Lambda   │  │    Lambda    │
                     └─────┬─────┘  └─────┬─────┘  └──────┬───────┘
                           │              │               │
                    presigned PUT         │               │
                           │              │               │
                           ▼              ▼               ▼
                     ┌──────────────┐  ┌──────────────────────┐
                     │  S3          │  │  DynamoDB            │
                     │  documents   │  │  ┌────────────────┐  │
                     └──────┬───────┘  │  │  records       │  │
                            │          │  │  audit         │  │
                    ObjectCreated      │  │  reference     │  │
                            │          │  └────────────────┘  │
                            ▼          └──────────────────────┘
                     ┌──────────────┐             ▲
                     │  EventBridge │             │
                     │   default    │             │
                     │  event bus   │             │
                     └──────┬───────┘             │
                            │                     │
                            ▼                     │
                     ┌──────────────┐             │
                     │ Step         │             │
                     │ Functions    │             │
                     │ (Express)    │             │
                     └──┬──┬──┬──┬──┘             │
                        │  │  │  │                │
              ┌─────────┘  │  │  └─────────┐      │
              ▼            ▼  ▼            ▼      │
        ┌──────────┐  ┌──────────┐  ┌───────────┐ │
        │   OCR    │  │ Bedrock  │  │Validation │ │
        │ Lambda   │  │ Extract  │  │ Lambda    │─┘
        │ (ECR)    │  │ Lambda   │  │ (Python)  │
        └──────────┘  └──────────┘  └───────────┘
```

**Cross-cutting:** CloudWatch Logs for every Lambda + Step Functions execution history. Cognito Identity Pool grants temporary IAM creds to the Amplify app for direct S3 uploads via presigned URLs.

---

## 3. Data flow (upload → decision)

1. Reviewer clicks **Upload** in the Amplify frontend.
2. Frontend calls `POST /documents/upload` (API Gateway → **Upload Lambda**) with `filename`, `content_type`, `size`.
3. Upload Lambda:
   - Validates size ≤ 20MB, mime in `{pdf,jpg,png}`
   - Creates a `document_id` (UUID) and `record_id` (ULID)
   - Writes a `PENDING` row to `records` table
   - Returns a **presigned S3 PUT URL** (5-minute expiry) scoped to key `raw/<document_id>.<ext>`
4. Frontend PUTs the file to S3.
5. S3 `ObjectCreated:Put` event → EventBridge default bus.
6. EventBridge rule matches `source=aws.s3` + prefix `raw/` and starts the Step Functions execution with input `{ bucket, key, document_id, record_id }`.
7. Step Functions:
   - **GetMetadata** — Lambda reads S3 head + `records` row
   - **OCR** — invokes OCR Lambda (container image from ECR)
   - **NormalizeOcr** — collapses whitespace, dehyphenates, detects language
   - **BedrockExtract** — Anthropic Claude via Bedrock, JSON schema output
   - **DeterministicParse** — Python regex/lookup for Khasra/Khata/dates/area (see Section 9 of the spec)
   - **Validate** — Validation Lambda hits `reference` table + applies rules
   - **CalculateConfidence** — weighted score (see `VALIDATION_RULES.md`)
   - **Decide** — Choice state on `overall_confidence`
   - **Persist** — updates `records` row with final `status`, fields, flags, confidence
8. Step Functions execution ends. No `waitForTaskToken`.
9. If `NEEDS_REVIEW`: the record shows up in the reviewer queue on next `GET /review-queue`.
10. Reviewer opens `GET /records/{id}`, sees the document (presigned GET URL) side-by-side with fields.
11. Reviewer edits a field → `PUT /records/{id}` → Review Lambda:
    - writes the correction
    - **synchronously** re-runs `Validate` + `CalculateConfidence` in-process
    - updates status + writes an `audit` row
12. Reviewer approves → `POST /records/{id}/approve` → status `HUMAN_APPROVED`, audit entry.

---

## 4. DynamoDB tables

### `records`

| Attribute | Type | Notes |
|---|---|---|
| `record_id` (PK) | S | ULID |
| `document_id` (GSI1 PK) | S | UUID matches S3 key |
| `owner_name_norm` (GSI2 PK) | S | lowercased, unaccented — search |
| `khasra_number` | S | e.g. `117/2` |
| `khata_number` | S | |
| `plot_number` | S | |
| `area` | N | canonical (m²) |
| `area_display` | S | e.g. `2.5 hectare` |
| `village` / `tehsil` / `district` / `state` | S | |
| `land_classification` | S | |
| `ownership_type` | S | |
| `mutation_date` | S | ISO 8601 |
| `registration_number` | S | |
| `extraction_confidence` | N | 0..1 |
| `validation_score` | N | 0..1 |
| `overall_confidence` | N | 0..100 |
| `validation_status` | S | `PENDING` / `AUTO_APPROVED` / `NEEDS_REVIEW` / `HIGH_RISK` / `HUMAN_APPROVED` / `REJECTED` |
| `validation_flags` | L (list of maps) | see `VALIDATION_RULES.md` |
| `field_confidence` | M | per-field 0..1 |
| `source_document_key` | S | S3 key |
| `created_at` / `updated_at` | S | ISO 8601 |

**GSIs:**
- `GSI1` on `document_id`
- `GSI2` on `owner_name_norm` (for search)
- `GSI3` on `validation_status` + `updated_at` (for review queue ordered by staleness)

### `audit`

| Attribute | Type | Notes |
|---|---|---|
| `record_id` (PK) | S | |
| `timestamp` (SK) | S | ISO 8601 with ms |
| `action` | S | `HUMAN_CORRECTION` / `HUMAN_APPROVED` / `REJECTED` / `AUTO_APPROVED` / `SYSTEM_REVALIDATE` |
| `field` | S | e.g. `area` |
| `old_value` | S | |
| `new_value` | S | |
| `user` | S | Cognito sub or email |

Sort descending by timestamp for latest-first history.

### `reference`

| Attribute | Type | Notes |
|---|---|---|
| `khasra_number` (PK) | S | e.g. `117/2` |
| `village_norm` (SK) | S | disambiguates same Khasra in different villages |
| `owner_name` | S | |
| `area` | N | canonical (m²) |
| `khata_number` / `district` / `state` etc. | S | |
| `source` | S | Always `SYNTHETIC_DEMO` for the hackathon |

---

## 5. IAM boundaries (least-privilege)

| Lambda | S3 | DynamoDB | Bedrock | Notes |
|---|---|---|---|---|
| Upload | `PutObject` on `raw/*` (presign only) | `PutItem` records | — | |
| OCR worker | `GetObject` on `raw/*` | — | — | Runs in container image |
| Extraction | — (receives OCR text from SFN) | — | `InvokeModel` on specific model ARNs | |
| Validation | — | `GetItem` reference, `Query` records (dup detect), `UpdateItem` records | — | |
| Review | `GetObject` on `raw/*` (presign for GET) | `UpdateItem` records, `PutItem` audit | — | |
| Dashboard | — | `Scan`/`Query` records with limits | — | |

No Lambda has `dynamodb:*` or `s3:*`. Every action is enumerated.

---

## 6. Frontend

- Next.js 14 App Router, TypeScript
- AWS Amplify Hosting (SSR on Lambda@Edge — verify current Amplify SSR support at deploy time)
- Auth: `aws-amplify` library with Cognito user pool
- Data fetching: SWR + fetch with Bearer token
- UI: Tailwind + shadcn/ui components
- Document viewer: `react-pdf` for PDF, plain `<img>` for JPG/PNG

Pages:

- `/login`
- `/dashboard` (metrics)
- `/upload`
- `/records` (search + filter)
- `/records/[id]` (side-by-side review UI)
- `/records/[id]/audit`

---

## 7. Observability

- CloudWatch Logs group per Lambda (`/aws/lambda/bhoomilens-<name>`)
- Step Functions execution history retained 90 days
- CloudWatch dashboard `BhoomiLens` with:
  - Documents uploaded / hour
  - Step Functions success vs failure
  - Bedrock invocation latency p50/p99
  - Validation Lambda duration
- CloudWatch alarm: Bedrock throttling → SNS email (optional)

---

## 8. What is intentionally NOT here

Per Section 2 of the spec:

- No full DILRMP integration
- No production government DB
- No portal scraping / CAPTCHA / OTP handling
- No custom model training (foundation or OCR)
- No Step Functions human-task-token pattern
- No microservices — just Lambdas
- No knowledge graph
- No multi-tenant RBAC (one Reviewer role)
