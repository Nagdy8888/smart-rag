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
  description = "EC2 instance role. OIDC deploy roles are Packet 2."
}
