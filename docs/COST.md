# BhoomiLens — Cost Rationale

## Budget target

**< $5/month** for the hackathon demo footprint (≈ 50 documents/day, 5 reviewers, ~1000 API calls/day).

**Hard cap: $20/month.** A CloudWatch billing alarm at $20 must exist before the first `cdk deploy`:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name bhoomilens-billing-cap \
  --alarm-description "Alert if BhoomiLens monthly bill exceeds $20" \
  --namespace AWS/Billing \
  --metric-name EstimatedCharges \
  --dimensions Name=Currency,Value=USD \
  --statistic Maximum \
  --period 21600 \
  --evaluation-periods 1 \
  --threshold 20 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:<account>:billing-alerts
```

Billing metrics live only in `us-east-1` — this is a known AWS quirk.

---

## Estimated line items (on-demand)

| Service | Unit price | Demo volume | Monthly |
|---|---|---|---|
| **Amazon Bedrock** (Claude Haiku 4.5, verify current price) | ~$0.001 / 1K input tokens, ~$0.005 / 1K output tokens | 50 docs/day × 30 = 1500 docs; ~2K in + 500 out tokens each | **~$3.00 – $4.50** |
| **AWS Lambda** | $0.20 per 1M requests, $0.0000166667 per GB-s | ~5000 invocations/mo, avg 512MB × 2s | **~$0.02 (free tier)** |
| **DynamoDB on-demand** | $1.25 per M writes, $0.25 per M reads | ~10K writes, 50K reads / mo | **~$0.02 (free tier)** |
| **Amazon S3** | $0.023/GB storage, $0.005/1K PUTs, $0.0004/1K GETs | ~5GB stored, 1.5K PUTs, 5K GETs | **~$0.15** |
| **API Gateway** (REST) | $3.50 per M calls | ~30K calls/mo | **~$0.11** |
| **Step Functions** (Express) | $1.00 per M state transitions | ~1500 executions × ~8 transitions = 12K | **~$0.01 (free tier)** |
| **EventBridge** | $1.00 per M events | 1500 events/mo | **~$0.00 (free tier)** |
| **Amazon Cognito** | first 50K MAUs free | 5 reviewers | **~$0.00** |
| **AWS Amplify Hosting** | $0.15/GB served + $0.01/build min | ~5GB served | **~$0.75** |
| **Amazon ECR** | $0.10/GB storage | ~1GB OCR image | **~$0.10** |
| **CloudWatch Logs** | $0.50/GB ingested | ~0.5GB | **~$0.25** |
| **Amazon Textract** (optional English fallback) | $1.50 per 1K pages | ~500 pages / mo (only if used) | **~$0.75** |
| | | **Total** | **~$5.00** |

Numbers are **illustrative**. Verify with the [AWS Pricing Calculator](https://calculator.aws) using current published prices for your region.

---

## Design decisions driven by cost

### Why Claude Haiku, not Opus / Sonnet by default
The extraction task is structured JSON output from ≤ 2K tokens of OCR text. Empirically Haiku hits ≥ 85% field accuracy on printed documents — the differential accuracy of Opus does not justify a 15× cost increase for the hackathon. Sonnet is used only as a *fallback* when Haiku returns low confidence (see `BEDROCK_MODEL_SELECTION.md`).

### Why Step Functions Express (not Standard)
- Cheaper at high volume ($1/M vs $25/M state transitions).
- Sub-5-minute workflows only — our pipeline finishes in < 15 seconds typically.
- If OCR ever exceeds 5 min, promote *that* state machine to Standard; don't upgrade the whole app.

### Why Lambda + ECR for OCR (not SageMaker / ECS Fargate)
- Fargate needs a warm task or slow cold start.
- SageMaker endpoints are billed per hour continuously — wrong shape for bursty demo traffic.
- Lambda container images give us on-demand billing plus a familiar deployment model.
- **Fallback:** if the OCR image exceeds Lambda's 10GB or the 15-min timeout is tight, promote OCR to Fargate; leave everything else on Lambda.

### Why DynamoDB (not RDS / Aurora)
- Pay-per-request with a real free tier.
- No idle cost.
- Single-digit-ms reads are more than enough — we're not doing analytical queries.
- The reference-registry access pattern is trivial: `get_item(PK, SK)`. No relational modeling needed.

### Why not caching Bedrock responses
For a hackathon at 50 docs/day, cache hit rate would be near zero. In production, hashing OCR text + prompt version and using DynamoDB as a cache would trim cost. Deliberately deferred.

### Why S3 + presigned URLs (not multipart-upload API through Lambda)
- Avoids sending file bytes through API Gateway (which has a 10MB request cap and is expensive per MB).
- Presigned URL is issued in one Lambda call; the actual bytes go direct to S3.
- Lambda concurrency isn't tied to upload speed.

---

## Cost pitfalls to watch

1. **Accidentally leaving CloudWatch Logs retention at "Never expire".** Set 14-day retention on every log group:
   ```typescript
   new logs.LogGroup(this, 'Log', {
     retention: logs.RetentionDays.TWO_WEEKS,
     removalPolicy: RemovalPolicy.DESTROY,
   });
   ```
2. **VPC-attached Lambdas** — none of our Lambdas need a VPC. Do not attach one. NAT costs would dominate the bill.
3. **`Scan` on DynamoDB** — the dashboard scan is bounded to 5000 items. Anything more than that must go through GSI queries.
4. **PaddleOCR base image size** — pruning to ~800MB keeps ECR storage under $0.10/mo. Do not ship a 5GB image.
5. **Bedrock retries** — the AWS SDK retries throttled requests. Set `max_attempts=2` on the boto3 client so a bad prompt doesn't cost 5× the intended budget.

---

## What the demo footprint intentionally does not include

- WAF ($5/mo baseline — not required for a hackathon demo, add for production)
- CloudFront in front of Amplify (Amplify already fronts with CloudFront; adding another distribution is wasteful)
- Multi-region replication (out of scope)
- Cross-account audit destination (out of scope)
