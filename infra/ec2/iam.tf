# Least-privilege instance role for Packet 1. GitHub OIDC deploy roles are Packet 2.

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
