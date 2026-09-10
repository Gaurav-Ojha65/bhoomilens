# BhoomiLens — 4-Day Implementation Plan

## Guiding rule

> Do not build features in parallel that depend on an untested architecture.
> Get **one** document through the full pipeline before adding polish.

---

## Day 0 — Pre-event preparation (**only** if permitted by hackathon rules)

Section 34 of the spec forbids competition implementation before the authorized start time. Pre-event work is limited to:

- Reading service docs (Bedrock, Step Functions, Amplify)
- Planning architecture (this doc, `ARCHITECTURE.md`, `BEDROCK_MODEL_SELECTION.md`)
- Preparing synthetic reference data
- Sandbox experiments in a personal AWS account **that will be discarded**

Do **not** commit code to the competition repo before authorization.

---

## Day 1 — Deploy the skeleton (P0 backbone)

**Goal:** every AWS service exists and is wired up, but the pipeline does nothing useful yet.

### Morning
- [ ] `cdk init` in `infrastructure/`
- [ ] `Storage` stack: S3 documents bucket, DynamoDB `records` / `audit` / `reference` tables, ECR repo
- [ ] `Auth` stack: Cognito user pool + client + identity pool
- [ ] Bootstrap + deploy both
- [ ] Verify Bedrock model access enabled and record ACTIVE model IDs (`docs/BEDROCK_MODEL_SELECTION.md`)

### Afternoon
- [ ] `Workflow` stack: EventBridge rule on S3, Step Functions state machine with stub Lambdas that just log input
- [ ] `Api` stack: API Gateway REST API with Cognito authorizer, one Lambda that returns `{"ok": true}`
- [ ] Deploy, then upload a random file to `raw/` prefix and confirm Step Functions execution appears in the console

**End-of-day acceptance:** upload a file → SFN execution runs stub tasks → no errors in CloudWatch.

---

## Day 2 — First real document end-to-end

**Goal:** one deliberately-controlled document goes through OCR → Bedrock → validation → DynamoDB.

### Morning
- [ ] OCR Lambda container: PaddleOCR base image, Python handler reads S3, returns `{text, pages, blocks, language, ocr_confidence}`
- [ ] Push to ECR (`ocr/build_and_push.sh`)
- [ ] Wire into Step Functions
- [ ] Test with 1 English document + 1 Hindi document

### Afternoon
- [ ] Bedrock Extraction Lambda: reads OCR output, calls Claude with `prompts/extraction_prompt.txt`, returns structured JSON
- [ ] Deterministic parse pass (Khasra regex, dates, area)
- [ ] Validation Lambda: reference lookup + deterministic rules (see `VALIDATION_RULES.md`), writes to `records`

**End-of-day acceptance:** upload the "clean" test document → record ends up in `records` table with status `AUTO_APPROVED` and correct fields.

---

## Day 3 — Review UI + validation depth

### Morning
- [ ] Upload the "area mismatch" test document → confirm `NEEDS_REVIEW` with `AREA_MISMATCH` flag
- [ ] Review Lambda: `GET /review-queue`, `GET /records/{id}`, `PUT /records/{id}`, revalidation, audit write
- [ ] Confidence calculation with configurable weights

### Afternoon
- [ ] Frontend scaffold (Next.js on Amplify Hosting)
- [ ] Login page (Cognito)
- [ ] Upload page (presigned URL flow)
- [ ] Records list with filters
- [ ] Record detail — side-by-side viewer, editable fields, validation flags
- [ ] Dashboard with real metrics from DynamoDB scan (bounded)

**End-of-day acceptance:** you can log in, upload the broken test doc, watch it hit `NEEDS_REVIEW`, correct the area, see it flip to `AUTO_APPROVED`, and see the audit entry.

---

## Day 4 — Polish, official-source, tests, deploy

### Morning
- [ ] Load `data/state_portals.json` — `[Open Official Land Record Portal]` button on record detail
- [ ] Loading states, error boundaries, empty states
- [ ] Field-level confidence display (green ≥90, amber 70–89, red <70)
- [ ] Search: owner, khasra, village

### Afternoon
- [ ] Run `scripts/evaluate.py` against `data/test_scenarios.json`, paste real numbers into README
- [ ] Fix top 3 bugs surfaced
- [ ] Record 3-minute demo video (see `DEMO_SCRIPT.md`)
- [ ] Draft AWS Builder Center write-up
- [ ] Final deploy — Amplify domain is your submission URL

**End-of-day acceptance:** deployed app has all 15 success criteria from Section 36 of the spec.

---

## Cut-list (drop in this order if behind schedule)

| Priority | Feature | Cut if you're behind by |
|---|---|---|
| P2 | Tamper/image-integrity signals | Any amount |
| P2 | Cadastral map preview | Any amount |
| P2 | Additional Indian languages beyond Hi/En | Any amount |
| P2 | Advanced analytics on dashboard | 4h+ behind |
| P1 | CSV/JSON export | 6h+ behind |
| P1 | Full search (fall back to Khasra-only lookup) | 8h+ behind |
| P1 | Audit UI (audit still written, just not shown) | 12h+ behind |
| P0 | Multilingual OCR (fall back to English-only demo) | Last resort |

**Never cut:**
- Real Step Functions pipeline (fake demos disqualify)
- Validation Lambda with real rules
- Review UI with real correction + revalidation
- Cognito auth
- Official-source link

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Bedrock model access denied in `ap-south-1` | M | Fall back to `us-east-1`; note in README |
| PaddleOCR container > 10GB Lambda image limit | M | Prune model files or move to ECS Fargate (see `FALLBACK.md` — TBD) |
| Hindi OCR quality too low to demo | H | Demo primarily with the English document; use Hindi to *demonstrate* graceful `NEEDS_REVIEW` fallback |
| Amplify SSR unavailable in region | L | Static export + S3+CloudFront |
| Step Functions Express duration cap (5min) | L | Switch that state machine to Standard if OCR is slow |
| Cognito hosted UI misconfigured | M | Use amplify auth UI components instead |
