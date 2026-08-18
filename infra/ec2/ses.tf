# SES sandbox identity and configuration set only. Do not request production
# access from Packet 1. Live identity verification is Blocked until apply.

resource "aws_ses_email_identity" "staging" {
  email = var.ses_from_email
}

resource "aws_ses_configuration_set" "staging" {
  name = "${var.project_name}-email"
}
