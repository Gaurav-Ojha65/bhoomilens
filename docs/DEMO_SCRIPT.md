# 3-Minute Demo Script

**Goal:** show that BhoomiLens is a *real* AWS pipeline that does something meaningfully different from vanilla OCR — it catches an inconsistency, routes it to a human, and hands off to the official portal.

**One record. One story.** Don't try to demo everything.

---

## Setup (before recording)

- [ ] Two browser tabs pre-opened:
  - Tab A: BhoomiLens app, logged in as `reviewer@example.com`, on `/upload`
  - Tab B: AWS Console → Step Functions → the BhoomiLens state machine, execution list view
- [ ] Reference registry already seeded — the demo document's Khasra exists there with different area
- [ ] Demo document file `demo_rampur_broken.pdf` on desktop
  - Owner: Ram Prasad (matches reference)
  - Khasra: 117/2 (matches reference)
  - Village: Rampur (matches reference)
  - **Area: 5.2 hectare** (reference says 2.5 — deliberate mismatch)

---

## Script

### 00:00 – 00:15 · Framing (spoken)

> "Traditional OCR digitizes a land record. That's not the hard part.
> The hard part is: can we trust the extracted data?
> BhoomiLens is an AWS-native platform that extracts, **validates**, and helps a human verify — without ever claiming the AI proves authenticity.
> Let me show you one document going through the pipeline."

### 00:15 – 00:30 · Upload

- Drop `demo_rampur_broken.pdf` onto the upload zone
- Point at the toast: *"Uploaded to S3 · document_id: 9b5c…"*

> "The browser gets a presigned URL from a Cognito-authenticated Lambda and PUTs the file directly to S3 — no bytes flow through my API."

### 00:30 – 00:55 · The pipeline is real

- Switch to Tab B (Step Functions)
- Refresh — a new execution is running
- Click into it, point at the visual graph as states light up green:
  `GetMetadata → OCR → NormalizeOcr → BedrockExtract → Validate → CalculateConfidence → Decide → Persist`

> "S3 emits an event to EventBridge, which starts a Step Functions execution. OCR runs in a Lambda container image from ECR. Bedrock — Claude — extracts structured fields. Then a Python Lambda applies deterministic validation rules against a reference registry in DynamoDB. This is happening for real, not a mocked-out demo screen."

### 00:55 – 01:20 · The record shows up as NEEDS_REVIEW

- Switch back to Tab A → click **Review Queue**
- The new record is at the top with a red `NEEDS_REVIEW` badge

> "The record didn't auto-approve. Why? Because validation caught something."

- Click the record → land on the side-by-side review view
- Point at the fields:
  - Owner ✅ 96%
  - Khasra ✅ 99%
  - Village ✅ 97%
  - **Area ⚠ 61% · AREA_MISMATCH**

> "Extraction confidence for the area is 61% because the OCR was ambiguous. And the validation engine flagged AREA_MISMATCH — the reference registry has this Khasra at 2.5 hectare, the extracted document says 5.2 hectare. That's a 108% difference. Way beyond our 10% tolerance."

### 01:20 – 01:45 · The human corrects it

- Click **Edit** on the area field
- Change `5.2` → `2.5`
- Click **Save**
- Watch the toast: *"Revalidated · AREA_MISMATCH resolved · status → AUTO_APPROVED · overall confidence 93"*

> "I correct the area. The Review Lambda writes the change, runs the validation rules again in-process, recalculates confidence, and updates the status. And — importantly — it wrote an audit entry."

### 01:45 – 02:00 · Audit trail

- Click **Audit History** tab
- Show:
  ```
  2026-09-10 14:22:03  HUMAN_CORRECTION  area: "5.2" → "2.5"  by reviewer@example.com
  2026-09-10 14:22:03  SYSTEM_REVALIDATE overall_confidence: 71 → 93
  2026-09-10 14:22:03  STATUS_CHANGE     NEEDS_REVIEW → AUTO_APPROVED
  2026-09-10 14:21:52  AUTO_INGEST       validation_flags: [AREA_MISMATCH]
  ```

> "Every human touch is recorded. This is the accountability trail — who changed what, when."

### 02:00 – 02:20 · Official-source handoff

- Scroll to the top of the record
- Click **Open Official Land Record Portal**
- A new tab opens on `https://upbhulekh.gov.in/`

> "BhoomiLens does not claim this document is authentic. That would be false. Instead, when the record is data-consistent, we hand the reviewer to the *actual* government portal for the state — here, UP Bhulekh — to do the final verification against the source of truth. No scraping, no CAPTCHA bypass. Just a link, at the right moment, to the right place."

### 02:20 – 02:45 · Architecture whip-around

- Open the AWS Console breadcrumb tour tab (pre-opened):
  - Cognito user pool with the reviewer
  - S3 bucket with `raw/` prefix
  - DynamoDB `records` table with the row
  - Step Functions execution history
  - ECR repo with the OCR image
  - Bedrock model access page showing the ACTIVE model

> "Under the hood: Amplify, Cognito, API Gateway, Lambda, S3, EventBridge, Step Functions, OCR on Lambda container from ECR, Bedrock, DynamoDB, CloudWatch. Serverless, event-driven, no long-running compute. Roughly five dollars a month at this footprint."

### 02:45 – 03:00 · Close

> "So — the pitch: AI does the repetitive extraction. Deterministic validation catches inconsistencies the model would happily miss. Humans handle uncertainty. And when it's time to prove something, we send you to the government portal — because that's the only source that can actually prove it.
>
> BhoomiLens. Extract. Validate. Verify."

---

## Backup document (if the primary fails during recording)

Same setup but different failure:

- File: `demo_owner_mismatch.pdf`
- Extracted owner: "Ramprasad Sharma"
- Reference owner: "Ram Prasad"
- Expected flag: `OWNER_MISMATCH` (medium — after normalization the two do not exact-match, and edit distance > 2)

The reviewer corrects the owner name → status flips to `HUMAN_APPROVED` (not AUTO_APPROVED, because the correction was manual — this distinction is visible in the audit trail).

---

## What NOT to demo

- No fake progress bars — everything shown must be a real AWS event.
- Do not open the DynamoDB console mid-demo to "prove" data was written. It kills pacing. Show one *outcome*, not one query.
- Do not claim the AI is "99% accurate". If asked, cite the numbers from `scripts/evaluate.py` output — real measured accuracy on `data/test_scenarios.json`.
- Do not claim government API integration. It does not exist.
