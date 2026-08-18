# Packet 3 egress/origin denial telemetry. hashicorp/aws 5.100
# aws_cloudwatch_log_group, aws_cloudwatch_log_metric_filter, and
# aws_cloudwatch_metric_alarm. Filter patterns match Caddy denial strings.
# Live log delivery and alarm notifications are not proven. Do not treat these
# resources as a delivered synthetic alert. Alarm actions stay disabled until
# Packet 5 owns routing. See
# https://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/FilterAndPatternSyntax.html

resource "aws_cloudwatch_log_group" "egress_denials" {
  name              = "/smart-rag/staging/egress-denials"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_metric_filter" "egress_denials" {
  name           = "${var.project_name}-egress-denials"
  log_group_name = aws_cloudwatch_log_group.egress_denials.name
  pattern        = "provider egress denied"

  metric_transformation {
    name      = "ProviderEgressDenials"
    namespace = "SmartRag/Staging"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "direct_origin_denials" {
  name           = "${var.project_name}-direct-origin-denials"
  log_group_name = aws_cloudwatch_log_group.egress_denials.name
  pattern        = "direct origin denied"

  metric_transformation {
    name      = "DirectOriginDenials"
    namespace = "SmartRag/Staging"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "egress_denials" {
  alarm_name          = "${var.project_name}-egress-denials"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ProviderEgressDenials"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Provider egress denial observed. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = false
}

data "aws_iam_policy_document" "egress_denial_logs" {
  statement {
    sid = "EgressDenialLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = [
      "${aws_cloudwatch_log_group.egress_denials.arn}:*"
    ]
  }
}

resource "aws_iam_role_policy" "egress_denial_logs" {
  name   = "${var.project_name}-egress-denial-logs"
  role   = aws_iam_role.staging_instance.id
  policy = data.aws_iam_policy_document.egress_denial_logs.json
}
