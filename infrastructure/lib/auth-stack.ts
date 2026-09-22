import { Stack, StackProps, CfnOutput, Duration } from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export interface AuthStackProps extends StackProps {
  documentsBucket: s3.IBucket;
}

/**
 * Cognito authentication + application roles.
 *
 * USER is the normal BhoomiLens role.
 * SUPERVISOR inherits normal application access and is granted additional
 * supervision capabilities by application authorization checks.
 */
export class AuthStack extends Stack {
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;
  public readonly identityPool: cognito.CfnIdentityPool;
  public readonly userGroup: cognito.CfnUserPoolGroup;
  public readonly supervisorGroup: cognito.CfnUserPoolGroup;

  constructor(scope: Construct, id: string, props: AuthStackProps) {
    super(scope, id, props);

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: 'bhoomilens-reviewers',
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
        fullname: { required: false, mutable: true },
      },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      mfa: cognito.Mfa.OPTIONAL,
      mfaSecondFactor: { sms: false, otp: true },
      deletionProtection: false,
    });

    this.userPoolClient = new cognito.UserPoolClient(this, 'UserPoolClient', {
      userPool: this.userPool,
      generateSecret: false,
      authFlows: { userPassword: true, userSrp: true },
      idTokenValidity: Duration.hours(1),
      accessTokenValidity: Duration.hours(1),
      refreshTokenValidity: Duration.days(30),
      preventUserExistenceErrors: true,
    });

    this.userGroup = new cognito.CfnUserPoolGroup(this, 'UserGroup', {
      userPoolId: this.userPool.userPoolId,
      groupName: 'USER',
      description: 'Standard BhoomiLens application user',
      precedence: 20,
    });

    this.supervisorGroup = new cognito.CfnUserPoolGroup(this, 'SupervisorGroup', {
      userPoolId: this.userPool.userPoolId,
      groupName: 'SUPERVISOR',
      description: 'BhoomiLens supervisor with additional supervision access',
      precedence: 10,
    });

    this.identityPool = new cognito.CfnIdentityPool(this, 'IdentityPool', {
      allowUnauthenticatedIdentities: false,
      cognitoIdentityProviders: [{
        clientId: this.userPoolClient.userPoolClientId,
        providerName: this.userPool.userPoolProviderName,
      }],
    });

    const authenticatedRole = new iam.Role(this, 'CognitoAuthenticatedRole', {
      assumedBy: new iam.FederatedPrincipal(
        'cognito-identity.amazonaws.com',
        {
          StringEquals: { 'cognito-identity.amazonaws.com:aud': this.identityPool.ref },
          'ForAnyValue:StringLike': { 'cognito-identity.amazonaws.com:amr': 'authenticated' },
        },
        'sts:AssumeRoleWithWebIdentity',
      ),
      description: 'BhoomiLens authenticated user role',
    });

    authenticatedRole.addToPolicy(new iam.PolicyStatement({
      actions: ['cognito-identity:GetCredentialsForIdentity'],
      resources: ['*'],
    }));

    new cognito.CfnIdentityPoolRoleAttachment(this, 'IdentityPoolRoles', {
      identityPoolId: this.identityPool.ref,
      roles: { authenticated: authenticatedRole.roleArn },
    });

    new CfnOutput(this, 'UserPoolId', { value: this.userPool.userPoolId });
    new CfnOutput(this, 'UserPoolClientId', { value: this.userPoolClient.userPoolClientId });
    new CfnOutput(this, 'IdentityPoolId', { value: this.identityPool.ref });
    new CfnOutput(this, 'UserGroupName', { value: this.userGroup.groupName! });
    new CfnOutput(this, 'SupervisorGroupName', { value: this.supervisorGroup.groupName! });
  }
}
