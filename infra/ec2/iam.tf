# Least-privilege instance role. GitHub OIDC roles live in oidc.tf (Packet 2).
# Packet 5 audit KMS: do not grant kms:Decrypt or kms:Sign on this role.
# The exporter job is a later principal. Database roles never receive the key.

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "staging_instance" {
  name               = "${var.project_name}-ec2"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.staging_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.staging_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

data "aws_iam_policy_document" "staging_secrets" {
  statement {
    sid     = "StagingSecretsGet"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.staging_secret_prefix}*"
    ]
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

resource "aws_iam_role_policy" "staging_secrets" {
  name   = "${var.project_name}-secrets"
  role   = aws_iam_role.staging_instance.id
  policy = data.aws_iam_policy_document.staging_secrets.json
}

resource "aws_iam_instance_profile" "staging" {
  name = "${var.project_name}-ec2"
  role = aws_iam_role.staging_instance.name
}
