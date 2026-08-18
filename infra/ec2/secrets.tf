# Secrets Manager placeholders only. Never commit secret values or versions.
# hashicorp/aws ~> 5.100 puts rotation_rules on aws_secretsmanager_secret_rotation,
# which requires a rotation Lambda for non-RDS secrets. This packet does not
# invent a Lambda. Custody is 90-day policy in locals/inventory plus IAM deny
# of long-lived access-key minting. Live rotation is Blocked.

locals {
  secret_rotation_max_days         = 90
  secret_rotation_lambda_present   = false
  secret_rotation_live_classified  = "Blocked"
}

resource "aws_secretsmanager_secret" "staging_db" {
  name                    = "${var.staging_secret_prefix}db"
  description             = "Staging database migration credential placeholder. Values are never in git."
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "production_db" {
  name                    = "${var.production_secret_prefix}db"
  description             = "Production database migration credential placeholder. Values are never in git."
  recovery_window_in_days = 7
}
