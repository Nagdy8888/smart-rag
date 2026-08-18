# Phase 10 Packet 1 reviewed IaC. Live apply is not proven from this repository
# clone: AWS session may be expired and Terraform/OpenTofu may be absent.
# Pin hashicorp/aws 5.x. Do not jump to AWS provider 6 in this packet.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
