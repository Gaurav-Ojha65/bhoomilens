import { Duration, RemovalPolicy, Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import { Construct } from 'constructs';

/**
 * All durable resources: S3 bucket for documents, three DynamoDB tables,
 * and the ECR repo for the OCR container image.
 *
 * Kept in a separate stack so it can be deployed once and left alone —
 * updates to Lambdas or API do not risk data loss.
 */
export class StorageStack extends Stack {
  public readonly documentsBucket: s3.Bucket;
  public readonly recordsTable: dynamodb.Table;
  public readonly referenceTable: dynamodb.Table;
  public readonly auditTable: dynamodb.Table;
  public readonly ocrEcrRepo: ecr.Repository;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // --------------------------------------------------------------------
    // S3: uploaded documents
    // --------------------------------------------------------------------
    this.documentsBucket = new s3.Bucket(this, 'DocumentsBucket', {
      // Bucket name is intentionally omitted so CDK generates a unique one.
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: false,
      eventBridgeEnabled: true, // sends S3 events to the default event bus
      lifecycleRules: [
        {
          id: 'ExpireOldUploads',
          prefix: 'raw/',
          expiration: Duration.days(90), // hackathon: 90-day retention
        },
      ],
      cors: [
        {
          allowedMethods: [
            s3.HttpMethods.PUT,
            s3.HttpMethods.GET,
            s3.HttpMethods.HEAD,
          ],
          allowedOrigins: ['*'], // tighten to Amplify domain after first deploy
          allowedHeaders: ['*'],
          exposedHeaders: ['ETag'],
          maxAge: 3000,
        },
      ],
      removalPolicy: RemovalPolicy.RETAIN, // never auto-delete a bucket with real data
    });

    // --------------------------------------------------------------------
    // DynamoDB: records
    // --------------------------------------------------------------------
    this.recordsTable = new dynamodb.Table(this, 'RecordsTable', {
      tableName: 'bhoomilens-records',
      partitionKey: { name: 'record_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    this.recordsTable.addGlobalSecondaryIndex({
      indexName: 'GSI1',
      partitionKey: { name: 'document_id', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    this.recordsTable.addGlobalSecondaryIndex({
      indexName: 'GSI2',
      partitionKey: { name: 'owner_name_norm', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'updated_at', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    this.recordsTable.addGlobalSecondaryIndex({
      indexName: 'GSI3',
      partitionKey: { name: 'validation_status', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'updated_at', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // --------------------------------------------------------------------
    // DynamoDB: reference registry (SYNTHETIC data)
    // --------------------------------------------------------------------
    this.referenceTable = new dynamodb.Table(this, 'ReferenceTable', {
      tableName: 'bhoomilens-reference',
      partitionKey: { name: 'khasra_number', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'village_norm', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: false,
      removalPolicy: RemovalPolicy.DESTROY, // reference data is regenerable
    });

    // --------------------------------------------------------------------
    // DynamoDB: audit trail
    // --------------------------------------------------------------------
    this.auditTable = new dynamodb.Table(this, 'AuditTable', {
      tableName: 'bhoomilens-audit',
      partitionKey: { name: 'record_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // --------------------------------------------------------------------
    // ECR: OCR container image
    // --------------------------------------------------------------------
    this.ocrEcrRepo = new ecr.Repository(this, 'OcrRepo', {
      repositoryName: 'bhoomilens-ocr',
      imageScanOnPush: true,
      lifecycleRules: [
        { maxImageCount: 5, description: 'Keep only the 5 most recent OCR images' },
      ],
      removalPolicy: RemovalPolicy.DESTROY, // images can be rebuilt
    });

    // --------------------------------------------------------------------
    // Outputs
    // --------------------------------------------------------------------
    new CfnOutput(this, 'DocumentsBucketName', { value: this.documentsBucket.bucketName });
    new CfnOutput(this, 'RecordsTableName', { value: this.recordsTable.tableName });
    new CfnOutput(this, 'ReferenceTableName', { value: this.referenceTable.tableName });
    new CfnOutput(this, 'AuditTableName', { value: this.auditTable.tableName });
    new CfnOutput(this, 'OcrEcrRepoUri', { value: this.ocrEcrRepo.repositoryUri });
  }
}
