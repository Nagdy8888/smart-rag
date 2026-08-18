# GitHub OIDC provider and environment-scoped roles. Deny-by-construction:
# wrong repo, missing environment, production on staging, and repo:* cannot
# assume. Live AssumeRoleWithWebIdentity is not executed from this repository.

data "aws_iam_policy_document" "staging_oidc_migrate_trust" {
  statement {
    sid     = "GitHubOidcStagingMigrate"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:staging"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:job_workflow_ref"
      values   = ["${var.github_repository}/.github/workflows/staging-migrate.yml@*"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:ref"
      values = [
        "refs/heads/main",
        "refs/tags/*",
      ]
    }
  }
}

data "aws_iam_policy_document" "staging_oidc_deploy_trust" {
  statement {
    sid     = "GitHubOidcStagingDeploy"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:staging"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:job_workflow_ref"
      values   = ["${var.github_repository}/.github/workflows/staging-deploy.yml@*"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:ref"
      values = [
        "refs/heads/main",
        "refs/tags/*",
      ]
    }
  }
}

data "aws_iam_policy_document" "production_oidc_migrate_trust" {
  statement {
    sid     = "GitHubOidcProductionMigrate"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:production"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:job_workflow_ref"
      values   = ["${var.github_repository}/.github/workflows/production-migrate.yml@*"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:ref"
      values = [
        "refs/heads/main",
        "refs/tags/*",
      ]
    }
  }
}

data "aws_iam_policy_document" "staging_oidc_migrate_permissions" {
  statement {
    sid     = "SendNamedMigrateDocument"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:document/SmartRagStagingMigrate"
    ]
  }

  statement {
    sid     = "SendCommandStagingInstances"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ec2:${var.aws_region}:*:instance/*"
    ]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Environment"
      values   = ["staging"]
    }
  }

  statement {
    sid       = "ReadCommandResult"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:*"]
  }

  statement {
    sid    = "DenyIAM"
    effect = "Deny"
    actions = [
      "iam:CreateAccessKey",
      "iam:CreateUser",
      "iam:CreateLoginProfile",
      "iam:*",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DenyProductionSecrets"
    effect = "Deny"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:PutSecretValue",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.production_secret_prefix}*"
    ]
  }
}

data "aws_iam_policy_document" "staging_oidc_deploy_permissions" {
  statement {
    sid     = "SendNamedDeployDocument"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:document/SmartRagStagingDeploy"
    ]
  }

  statement {
    sid     = "SendCommandStagingInstances"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ec2:${var.aws_region}:*:instance/*"
    ]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Environment"
      values   = ["staging"]
    }
  }

  statement {
    sid       = "ReadCommandResult"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:*"]
  }

  statement {
    sid    = "DenyIAM"
    effect = "Deny"
    actions = [
      "iam:CreateAccessKey",
      "iam:CreateUser",
      "iam:*",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DenyProductionSecrets"
    effect = "Deny"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:PutSecretValue",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.production_secret_prefix}*"
    ]
  }
}

data "aws_iam_policy_document" "production_oidc_migrate_permissions" {
  statement {
    sid     = "SendNamedProductionMigrateDocument"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:document/SmartRagProductionMigrate"
    ]
  }

  statement {
    sid     = "SendCommandProductionInstances"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ec2:${var.aws_region}:*:instance/*"
    ]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Environment"
      values   = ["production"]
    }
  }

  statement {
    sid       = "ReadCommandResult"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:*"]
  }

  statement {
    sid    = "DenyIAM"
    effect = "Deny"
    actions = [
      "iam:CreateAccessKey",
      "iam:CreateUser",
      "iam:*",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DenyStagingSecretWriteFromProductionRole"
    effect = "Deny"
    actions = [
      "secretsmanager:PutSecretValue",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.staging_secret_prefix}*"
    ]
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
  client_id_list = [
    "sts.amazonaws.com",
  ]
  # GitHub is in the AWS trusted-root OIDC set; thumbprints are retained for
  # explicit review. Source: GitHub Actions AWS OIDC docs.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

resource "aws_iam_role" "staging_oidc_migrate" {
  name               = "${var.project_name}-oidc-migrate"
  assume_role_policy = data.aws_iam_policy_document.staging_oidc_migrate_trust.json
}

resource "aws_iam_role_policy" "staging_oidc_migrate" {
  name   = "${var.project_name}-oidc-migrate"
  role   = aws_iam_role.staging_oidc_migrate.id
  policy = data.aws_iam_policy_document.staging_oidc_migrate_permissions.json
}

resource "aws_iam_role" "staging_oidc_deploy" {
  name               = "${var.project_name}-oidc-deploy"
  assume_role_policy = data.aws_iam_policy_document.staging_oidc_deploy_trust.json
}

resource "aws_iam_role_policy" "staging_oidc_deploy" {
  name   = "${var.project_name}-oidc-deploy"
  role   = aws_iam_role.staging_oidc_deploy.id
  policy = data.aws_iam_policy_document.staging_oidc_deploy_permissions.json
}

resource "aws_iam_role" "production_oidc_migrate" {
  name               = "${var.production_project_name}-oidc-migrate"
  assume_role_policy = data.aws_iam_policy_document.production_oidc_migrate_trust.json
}

resource "aws_iam_role_policy" "production_oidc_migrate" {
  name   = "${var.production_project_name}-oidc-migrate"
  role   = aws_iam_role.production_oidc_migrate.id
  policy = data.aws_iam_policy_document.production_oidc_migrate_permissions.json
}
