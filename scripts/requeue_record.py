#!/usr/bin/env python3
"""Re-run the ingest state machine for a specific record.

Useful when a record failed mid-pipeline (e.g., Bedrock throttled) and
you want to reprocess without re-uploading. Reads the source document
key from DynamoDB, then starts the state machine.

  python scripts/requeue_record.py --record-id REC-... --region ap-south-1
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import boto3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-south-1"))
    ap.add_argument("--state-machine-name", default="bhoomilens-ingest")
    ap.add_argument("--records-table", default="bhoomilens-records")
    ap.add_argument("--documents-bucket", default=os.environ.get("DOCUMENTS_BUCKET"))
    args = ap.parse_args()

    session = boto3.Session(region_name=args.region)
    ddb = session.resource("dynamodb").Table(args.records_table)
    sfn = session.client("stepfunctions")
    sts = session.client("sts")

    row = ddb.get_item(Key={"record_id": args.record_id}).get("Item")
    if not row:
        print(f"Record {args.record_id} not found", file=sys.stderr)
        return 1

    key = row.get("source_document_key")
    bucket = args.documents_bucket
    if not bucket:
        print("Set --documents-bucket or $DOCUMENTS_BUCKET", file=sys.stderr)
        return 1
    if not key:
        print(f"Record {args.record_id} has no source_document_key", file=sys.stderr)
        return 1

    account = sts.get_caller_identity()["Account"]
    sm_arn = f"arn:aws:states:{args.region}:{account}:stateMachine:{args.state_machine_name}"

    payload = {
        "bucket": bucket,
        "key": key,
        "size": 0,
        "eventTime": "manual-requeue",
    }
    resp = sfn.start_execution(stateMachineArn=sm_arn, input=json.dumps(payload))
    print(f"Started execution: {resp['executionArn']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
