# Named SSM Command documents. OIDC roles may SendCommand only to these names
# and Environment-tagged instances. Documents fetch secrets via the instance
# role, never via GitHub.

resource "aws_ssm_document" "staging_migrate" {
  name            = "SmartRagStagingMigrate"
  document_type   = "Command"
  document_format = "YAML"
  content         = file("${path.module}/ssm-documents/staging-migrate.yml")
}

resource "aws_ssm_document" "staging_deploy" {
  name            = "SmartRagStagingDeploy"
  document_type   = "Command"
  document_format = "YAML"
  content         = file("${path.module}/ssm-documents/staging-deploy.yml")
}

resource "aws_ssm_document" "production_migrate" {
  name            = "SmartRagProductionMigrate"
  document_type   = "Command"
  document_format = "YAML"
  content         = file("${path.module}/ssm-documents/production-migrate.yml")
}
