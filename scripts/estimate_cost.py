#!/usr/bin/env python3
"""Rough monthly-cost estimator for the BhoomiLens deployment.

Uses public list prices as of the last time this file was updated.
Verify with the AWS Pricing Calculator before making any planning
decision — this is a sanity check, not a quote.

Usage:
  python scripts/estimate_cost.py --daily-documents 50 --avg-ocr-pages 2
"""

from __future__ import annotations

import argparse


# All prices are USD, on-demand, ap-south-1 unless noted otherwise.
# Update these as pricing changes. Placeholder-shaped values are labelled.
PRICES = {
    # Bedrock — placeholder-shaped, MUST verify current price for the model actually used
    "bedrock_input_per_1k_tokens": 0.001,
    "bedrock_output_per_1k_tokens": 0.005,
    # Lambda
    "lambda_request_per_million": 0.20,
    "lambda_gb_second": 0.0000166667,
    # DynamoDB on-demand
    "ddb_write_per_million": 1.25,
    "ddb_read_per_million": 0.25,
    # S3
    "s3_storage_per_gb": 0.023,
    "s3_put_per_1k": 0.005,
    "s3_get_per_1k": 0.0004,
    # API Gateway (REST)
    "apigw_per_million": 3.50,
    # Step Functions Express
    "sfn_state_transition_per_million": 1.00,
    # Amplify Hosting
    "amplify_gb_served": 0.15,
    # ECR
    "ecr_storage_per_gb": 0.10,
    # CloudWatch Logs
    "cw_logs_ingest_per_gb": 0.50,
}


def estimate(daily_docs: int, avg_pages: int) -> dict:
    monthly_docs = daily_docs * 30

    # Bedrock: ~2K input + 500 output tokens per document (rough)
    input_tokens = monthly_docs * 2000 * avg_pages
    output_tokens = monthly_docs * 500 * avg_pages
    bedrock_cost = (
        (input_tokens / 1000) * PRICES["bedrock_input_per_1k_tokens"]
        + (output_tokens / 1000) * PRICES["bedrock_output_per_1k_tokens"]
    )

    # Lambda: 5 invocations per doc (upload, ocr, extract, validate, persist)
    # + ~1000 API calls / day for browsing
    lambda_invocations = monthly_docs * 5 + 30 * 1000
    lambda_gb_seconds = (
        monthly_docs * (0.5 * 15 + 3 * 30 + 0.5 * 3 + 0.5 * 5 + 0.25 * 3)  # per-Lambda MB*seconds sum
        / 1024  # MB -> GB-seconds combined estimate; heuristic only
    )
    lambda_cost = (
        (lambda_invocations / 1_000_000) * PRICES["lambda_request_per_million"]
        + lambda_gb_seconds * PRICES["lambda_gb_second"]
    )

    # DynamoDB: ~5 writes + 20 reads per doc
    ddb_writes = monthly_docs * 5
    ddb_reads = monthly_docs * 20
    ddb_cost = (
        (ddb_writes / 1_000_000) * PRICES["ddb_write_per_million"]
        + (ddb_reads / 1_000_000) * PRICES["ddb_read_per_million"]
    )

    # S3: assume 2MB average, 1 PUT, 3 GETs per doc, keep 90 days
    s3_gb_stored = (monthly_docs * 2 / 1024) * 3  # 3 months retained
    s3_cost = (
        s3_gb_stored * PRICES["s3_storage_per_gb"]
        + (monthly_docs * 1 / 1000) * PRICES["s3_put_per_1k"]
        + (monthly_docs * 3 / 1000) * PRICES["s3_get_per_1k"]
    )

    # API Gateway: ~30 requests per doc (uploads, browsing, review)
    apigw_calls = monthly_docs * 30
    apigw_cost = (apigw_calls / 1_000_000) * PRICES["apigw_per_million"]

    # Step Functions Express: ~8 transitions per doc
    sfn_transitions = monthly_docs * 8
    sfn_cost = (sfn_transitions / 1_000_000) * PRICES["sfn_state_transition_per_million"]

    # Amplify Hosting: 5GB/month served
    amplify_cost = 5 * PRICES["amplify_gb_served"]

    # ECR: ~1GB image
    ecr_cost = 1 * PRICES["ecr_storage_per_gb"]

    # CloudWatch Logs: 0.5GB
    cw_cost = 0.5 * PRICES["cw_logs_ingest_per_gb"]

    total = (
        bedrock_cost + lambda_cost + ddb_cost + s3_cost
        + apigw_cost + sfn_cost + amplify_cost + ecr_cost + cw_cost
    )

    return {
        "assumptions": {
            "daily_documents": daily_docs,
            "avg_pages_per_doc": avg_pages,
            "monthly_documents": monthly_docs,
        },
        "line_items": {
            "bedrock": round(bedrock_cost, 2),
            "lambda": round(lambda_cost, 2),
            "dynamodb": round(ddb_cost, 2),
            "s3": round(s3_cost, 2),
            "api_gateway": round(apigw_cost, 2),
            "step_functions": round(sfn_cost, 2),
            "amplify": round(amplify_cost, 2),
            "ecr": round(ecr_cost, 2),
            "cloudwatch": round(cw_cost, 2),
        },
        "total_monthly_usd": round(total, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily-documents", type=int, default=50)
    ap.add_argument("--avg-ocr-pages", type=int, default=2)
    args = ap.parse_args()

    result = estimate(args.daily_documents, args.avg_ocr_pages)

    print(f"Assumptions: {result['assumptions']}")
    print("-" * 44)
    for k, v in result["line_items"].items():
        print(f"  {k:20s}  ${v:>7.2f}")
    print("-" * 44)
    print(f"  TOTAL:              ${result['total_monthly_usd']:>7.2f}/month")
    print()
    print("NOTE: pricing is illustrative and MUST be re-verified with")
    print("https://calculator.aws before making planning decisions.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
