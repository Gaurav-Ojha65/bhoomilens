#!/usr/bin/env bash
# End-to-end deploy: infrastructure → OCR image → seed reference data.
#
# Prereqs (see README):
#   - AWS credentials with permissions to create the stacks
#   - Bedrock model access enabled for the models in .env
#   - Docker Desktop running (for the OCR image)
#   - Node + Python installed
#
# Idempotent — re-running skips steps that are already up to date.

set -euo pipefail

# Load .env if present so BEDROCK_MODEL_ID_* etc. are visible to CDK.
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

: "${AWS_REGION:=ap-south-1}"
: "${AWS_ACCOUNT_ID:=$(aws sts get-caller-identity --query Account --output text)}"
export AWS_REGION AWS_ACCOUNT_ID
export CDK_DEFAULT_REGION="${AWS_REGION}"
export CDK_DEFAULT_ACCOUNT="${AWS_ACCOUNT_ID}"

echo "==> Verifying Bedrock model access"
if [[ -z "${BEDROCK_MODEL_ID_PRIMARY:-}" || "${BEDROCK_MODEL_ID_PRIMARY}" == "PLACEHOLDER_VERIFY_ACTIVE" ]]; then
  echo "ERROR: set BEDROCK_MODEL_ID_PRIMARY in .env after running:"
  echo "  aws bedrock list-foundation-models --region ${AWS_REGION} \\"
  echo "    --by-inference-type ON_DEMAND --by-provider Anthropic \\"
  echo "    --query \"modelSummaries[?modelLifecycle.status=='ACTIVE'].[modelId]\" --output text"
  exit 1
fi

echo "==> CDK bootstrap (idempotent)"
cd infrastructure
npm install --silent
npx cdk bootstrap "aws://${AWS_ACCOUNT_ID}/${AWS_REGION}"

echo "==> Deploying Storage stack"
npx cdk deploy BhoomiLens-Storage --require-approval never

echo "==> Building + pushing OCR container to ECR"
cd ..
bash ocr/build_and_push.sh

echo "==> Deploying Auth stack"
cd infrastructure
npx cdk deploy BhoomiLens-Auth --require-approval never

echo "==> Deploying Workflow stack (depends on ECR image)"
npx cdk deploy BhoomiLens-Workflow --require-approval never

echo "==> Deploying Api stack"
npx cdk deploy BhoomiLens-Api --require-approval never

echo "==> Seeding synthetic reference registry"
cd ..
python scripts/seed_reference_data.py \
  --table bhoomilens-reference \
  --region "${AWS_REGION}" \
  --file data/reference_registry.json

echo
echo "==> Done. Grab the CloudFormation outputs for .env:"
aws cloudformation describe-stacks --stack-name BhoomiLens-Api \
  --query "Stacks[0].Outputs" --output table --region "${AWS_REGION}"
aws cloudformation describe-stacks --stack-name BhoomiLens-Auth \
  --query "Stacks[0].Outputs" --output table --region "${AWS_REGION}"
