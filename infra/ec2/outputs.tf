# Non-secret outputs only. Origin header values and database URLs stay out.

output "aws_region" {
  value       = var.aws_region
  description = "Intended AWS region."
}

output "vpc_id" {
  value       = aws_vpc.staging.id
  description = "Staging VPC id after apply. Not proven in Packet 1."
}

output "origin_security_group_id" {
  value       = aws_security_group.origin.id
  description = "Origin SG that allows CloudFront prefix-list HTTPS only."
}

output "instance_id" {
  value       = aws_instance.staging.id
  description = "EC2 origin instance id after apply."
}

output "origin_eip" {
  value       = aws_eip.origin.public_ip
  description = "Elastic IP for Caddy. Direct origin must still fail Packet 3."
}

output "cloudfront_domain_name" {
  value       = aws_cloudfront_distribution.api.domain_name
  description = "CloudFront domain. Live CDN stream is Packet 3/4."
}

output "waf_acl_arn" {
  value       = aws_wafv2_web_acl.staging.arn
  description = "WAFv2 web ACL ARN associated with CloudFront."
}

output "ecr_repository_urls" {
  value       = { for name, repo in aws_ecr_repository.app : name => repo.repository_url }
  description = "ECR URLs for digest-pinned application images."
}

output "ses_configuration_set" {
  value       = aws_ses_configuration_set.staging.name
  description = "Sandbox SES configuration set name."
}

output "instance_role_name" {
  value       = aws_iam_role.staging_instance.name
  description = "EC2 instance role. Fetches staging secrets for one-shot SSM jobs."
}

output "github_oidc_provider_arn" {
  value       = aws_iam_openid_connect_provider.github.arn
  description = "GitHub OIDC provider ARN after apply. Live assume is not proven here."
}

output "staging_oidc_migrate_role_arn" {
  value       = aws_iam_role.staging_oidc_migrate.arn
  description = "Staging migrate OIDC role. Store as GitHub environment var, not a secret."
}

output "staging_oidc_deploy_role_arn" {
  value       = aws_iam_role.staging_oidc_deploy.arn
  description = "Staging deploy OIDC role. Store as GitHub environment var, not a secret."
}

output "production_oidc_migrate_role_arn" {
  value       = aws_iam_role.production_oidc_migrate.arn
  description = "Production migrate OIDC role. Live production assume remains Blocked."
}

output "staging_migrate_document_name" {
  value       = aws_ssm_document.staging_migrate.name
  description = "Named SSM migrate document the staging OIDC role may invoke."
}

output "secret_rotation_max_days" {
  value       = local.secret_rotation_max_days
  description = "Custody maximum days between rotations. Live rotation Lambda is absent."
}
