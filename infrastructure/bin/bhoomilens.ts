#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { StorageStack } from '../lib/storage-stack';
import { AuthStack } from '../lib/auth-stack';
import { WorkflowStack } from '../lib/workflow-stack';
import { ApiStack } from '../lib/api-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT ?? process.env.AWS_ACCOUNT_ID,
  region: process.env.CDK_DEFAULT_REGION ?? process.env.AWS_REGION ?? 'ap-south-1',
};

// Bedrock model IDs — MUST be verified ACTIVE at deploy time.
// See docs/BEDROCK_MODEL_SELECTION.md for the procedure.
const bedrockPrimary =
  process.env.BEDROCK_MODEL_ID_PRIMARY ?? 'PLACEHOLDER_VERIFY_ACTIVE';
const bedrockFallback =
  process.env.BEDROCK_MODEL_ID_FALLBACK ?? 'PLACEHOLDER_VERIFY_ACTIVE';
const bedrockRegion = process.env.BEDROCK_REGION ?? env.region;

const storage = new StorageStack(app, 'BhoomiLens-Storage', { env });

const auth = new AuthStack(app, 'BhoomiLens-Auth', {
  env,
  documentsBucket: storage.documentsBucket,
});

const workflow = new WorkflowStack(app, 'BhoomiLens-Workflow', {
  env,
  documentsBucket: storage.documentsBucket,
  recordsTable: storage.recordsTable,
  referenceTable: storage.referenceTable,
  auditTable: storage.auditTable,
  ocrEcrRepo: storage.ocrEcrRepo,
  bedrockPrimaryModelId: bedrockPrimary,
  bedrockFallbackModelId: bedrockFallback,
  bedrockRegion,
});

new ApiStack(app, 'BhoomiLens-Api', {
  env,
  documentsBucket: storage.documentsBucket,
  recordsTable: storage.recordsTable,
  referenceTable: storage.referenceTable,
  auditTable: storage.auditTable,
  userPool: auth.userPool,
  bedrockPrimaryModelId: bedrockPrimary,
  bedrockFallbackModelId: bedrockFallback,
  bedrockRegion,
});

app.synth();
