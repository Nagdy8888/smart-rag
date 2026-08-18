# CloudFront + WAFv2 for the FastAPI/SSE origin. Cache policy CachingDisabled
# (4135ea2d-6df8-44a3-9df3-4b5a84be39ad) so API/SSE responses are not cached.
# Origin request policy AllViewerExceptHostHeader forwards Authorization.
#
# Timeouts: AWS CloudFront API CustomOriginConfig allows OriginReadTimeout
# 1-120 (default 30) and OriginKeepaliveTimeout 1-300 (default 5). See
# https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_CustomOriginConfig.html
# Terraform AWS provider 5.100 website still mentions a default upper bound of
# 60. Encode 90 anyway; live apply uses the AWS API contract. Do not lower to 60.

locals {
  origin_id                      = "ec2-caddy"
  caching_disabled_policy_id     = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  all_viewer_except_host_policy  = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
}

resource "aws_wafv2_web_acl" "staging" {
  name        = "${var.project_name}-api"
  description = "Managed staging WAF for CloudFront API/SSE"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "aws-common"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use {
            count {}
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "aws-known-bad-inputs"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "aws-ip-reputation"
    priority = 3
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "rate-limit"
    priority = 4
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-waf"
    sampled_requests_enabled   = true
  }
}

resource "aws_cloudfront_distribution" "api" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.project_name} API/SSE origin"
  web_acl_id      = aws_wafv2_web_acl.staging.arn
  price_class     = "PriceClass_100"
  http_version    = "http2"

  origin {
    domain_name = var.origin_hostname
    origin_id   = local.origin_id

    custom_origin_config {
      http_port                = 443
      https_port               = 443
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 90
      origin_keepalive_timeout = 90
    }

    custom_header {
      name  = var.origin_header_name
      value = var.origin_header_value
    }

    # Second header only when the previous name/value differ so Packet 4 can
    # overlap during rotation. Caddy always accepts current and previous values.
    dynamic "custom_header" {
      for_each = (
        var.origin_header_name_previous != var.origin_header_name ||
        var.origin_header_value_previous != var.origin_header_value
      ) ? [1] : []
      content {
        name  = var.origin_header_name_previous
        value = var.origin_header_value_previous
      }
    }
  }

  default_cache_behavior {
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    target_origin_id         = local.origin_id
    viewer_protocol_policy   = "https-only"
    compress                 = false
    cache_policy_id          = local.caching_disabled_policy_id
    origin_request_policy_id = local.all_viewer_except_host_policy
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
