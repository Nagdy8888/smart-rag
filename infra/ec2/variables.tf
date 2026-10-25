# Non-secret defaults only. Origin header name/value have no defaults.

variable "aws_region" {
  type        = string
  description = "Intended AWS region for production-equivalent staging topology."
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Name prefix for staging resources."
  default     = "smart-rag-staging"
}

variable "instance_type" {
  type        = string
  description = "Accepted staging EC2 type (t3.micro). Packet 5 load is not claimed."
  default     = "t3.micro"
}

variable "origin_hostname" {
  type        = string
  description = "Public hostname CloudFront uses to reach Caddy. Placeholder until DNS exists."
  default     = "origin.staging.example.invalid"
}

variable "origin_protocol_policy" {
  type        = string
  description = "CloudFront-to-origin protocol. Private API traffic requires certificate-backed HTTPS."
  default     = "https-only"

  validation {
    condition     = var.origin_protocol_policy == "https-only"
    error_message = "origin_protocol_policy must be https-only; HTTP exposes bearer credentials and private responses."
  }
}

variable "ses_from_email" {
  type        = string
  description = "Sandbox-verified sender identity. Not a production domain."
  default     = "staging-alerts@example.invalid"
}

variable "origin_header_name" {
  type        = string
  description = "CloudFront custom origin header name. Set at apply; never commit the value."
  sensitive   = true
}

variable "origin_header_value" {
  type        = string
  description = "Current CloudFront origin header value. Set at apply; never commit."
  sensitive   = true
}

variable "origin_header_name_previous" {
  type        = string
  description = "Previous origin header name during dual rotation overlap."
  sensitive   = true
}

variable "origin_header_value_previous" {
  type        = string
  description = "Previous origin header value. Caddy must accept this and the current value."
  sensitive   = true
}

variable "staging_secret_prefix" {
  type        = string
  description = "Secrets Manager name prefix the instance role may read."
  default     = "smart-rag/staging/"
}

variable "production_secret_prefix" {
  type        = string
  description = "Production Secrets Manager prefix. Staging roles must not read it."
  default     = "smart-rag/production/"
}

variable "github_repository" {
  type        = string
  description = "GitHub owner/name trusted by OIDC. Wrong repos cannot assume."
  default     = "Nagdy8888/Demo_Project_3"
}

variable "production_project_name" {
  type        = string
  description = "Name prefix for production OIDC/SSM resources."
  default     = "smart-rag-production"
}
