# Packet 5 staging audit anchors. hashicorp/aws ~> 5.100
# aws_kms_key + aws_kms_key_policy, aws_s3_bucket.object_lock_enabled (boolean),
# aws_s3_bucket_versioning, aws_s3_bucket_object_lock_configuration (not the
# deprecated nested object_lock_configuration block on aws_s3_bucket),
# aws_s3_bucket_server_side_encryption_configuration, public access block.
# Key material is never committed. Live PutObject / GetObject of a KMS-signed
# chain head is Blocked until apply. Local HMAC export is not KMS.
# The exporter job is a later principal: do not grant kms:Decrypt or kms:Sign
# on aws_iam_role.staging_instance, and do not grant this key to database roles.

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "audit" {
  description             = "Staging audit-chain envelope encryption. Exporter job is a later principal."
  enable_key_rotation     = true
  deletion_window_in_days = 30
  key_usage               = "ENCRYPT_DECRYPT"
}

data "aws_iam_policy_document" "audit_kms" {
  statement {
    sid    = "EnableRootAccountAdministration"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowS3SseKmsViaService"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${var.aws_region}.amazonaws.com"]
    }
  }

  statement {
    sid    = "DenyInstanceDecryptSign"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.staging_instance.arn]
    }
    actions = [
      "kms:Decrypt",
      "kms:Sign",
    ]
    resources = ["*"]
  }
}

resource "aws_kms_key_policy" "audit" {
  key_id = aws_kms_key.audit.id
  policy = data.aws_iam_policy_document.audit_kms.json
}

resource "aws_s3_bucket" "audit_anchors" {
  bucket              = "${var.project_name}-audit-anchors"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "audit_anchors" {
  bucket = aws_s3_bucket.audit_anchors.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "audit_anchors" {
  bucket = aws_s3_bucket.audit_anchors.id

  rule {
    default_retention {
      mode  = "GOVERNANCE"
      years = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.audit_anchors]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_anchors" {
  bucket = aws_s3_bucket.audit_anchors.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.audit.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit_anchors" {
  bucket                  = aws_s3_bucket.audit_anchors.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
