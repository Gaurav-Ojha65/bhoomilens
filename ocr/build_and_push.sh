#!/usr/bin/env bash
# Build the OCR container image and push it to the ECR repo created by
# BhoomiLens-Storage. Run this whenever ocr/Dockerfile or ocr/handler.py
# changes.
#
# Prereqs:
#   - AWS CLI configured
#   - Docker Desktop running
#   - BhoomiLens-Storage stack deployed (creates the ECR repo)

set -euo pipefail

: "${AWS_REGION:=ap-south-1}"
: "${AWS_ACCOUNT_ID:=$(aws sts get-caller-identity --query Account --output text)}"

REPO_NAME="bhoomilens-ocr"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${REGISTRY}/${REPO_NAME}:${IMAGE_TAG}"

echo "-> Logging in to ${REGISTRY}"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

echo "-> Building image (platform: linux/amd64 — required for Lambda)"
docker build \
  --platform linux/amd64 \
  -f ocr/Dockerfile \
  -t "${IMAGE_URI}" \
  .

echo "-> Pushing image ${IMAGE_URI}"
docker push "${IMAGE_URI}"

echo "-> Done. Update the Lambda if it was created before this image existed:"
echo "   aws lambda update-function-code \\"
echo "     --function-name bhoomilens-ocr \\"
echo "     --image-uri ${IMAGE_URI}"
