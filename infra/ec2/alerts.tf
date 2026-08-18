# Packet 5 staging operational and billing alarm routing. hashicorp/aws ~> 5.100
# aws_sns_topic.staging_ops has no production email subscriptions.
# aws_budgets_budget COST USD MONTHLY notifies SNS only (bounded 50 USD).
# Additional CloudWatch alarms are committed policy placeholders. Live SNS
# delivery, acknowledgement, and escalation remain Blocked until apply.

resource "aws_sns_topic" "staging_ops" {
  name = "${var.project_name}-ops"
}

# CloudWatch alarms and AWS Budgets cannot publish without a topic policy.
# Live delivery remains Blocked until apply. No email subscriptions.
data "aws_iam_policy_document" "staging_ops_sns" {
  statement {
    sid    = "AllowCloudWatchAlarms"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.staging_ops.arn]
  }

  statement {
    sid    = "AllowAwsBudgets"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.staging_ops.arn]
  }
}

resource "aws_sns_topic_policy" "staging_ops" {
  arn    = aws_sns_topic.staging_ops.arn
  policy = data.aws_iam_policy_document.staging_ops_sns.json
}

resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name          = "${var.project_name}-cpu"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "CpuUtilizationPlaceholder"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Average"
  threshold           = 70
  alarm_description   = "CPU placeholder. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "memory" {
  alarm_name          = "${var.project_name}-memory"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "MemoryUtilizationPlaceholder"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Average"
  threshold           = 70
  alarm_description   = "Memory placeholder. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "disk" {
  alarm_name          = "${var.project_name}-disk"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "DiskUtilizationPlaceholder"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Average"
  threshold           = 70
  alarm_description   = "Disk placeholder. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "paradedb_fallback" {
  alarm_name          = "${var.project_name}-paradedb-fallback"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ParadeDBFallback"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "ParadeDB fallback observed. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "valkey" {
  alarm_name          = "${var.project_name}-valkey"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ValkeyMemoryOrRejections"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "Valkey memory or rejection placeholder. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "audit_anchor_gap" {
  alarm_name          = "${var.project_name}-audit-anchor-gap"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "AuditAnchorGap"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Audit-anchor gap placeholder. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "ses_bounce" {
  alarm_name          = "${var.project_name}-ses-bounce"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "SesBounces"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "SES bounce placeholder. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "openai_spend_proxy" {
  alarm_name          = "${var.project_name}-openai-spend-proxy"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "OpenAISpendProxyUSD"
  namespace           = "SmartRag/Staging"
  period              = 60
  statistic           = "Maximum"
  threshold           = 20
  alarm_description   = "OpenAI spend proxy placeholder. Live delivery is Blocked."
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.staging_ops.arn]
}

resource "aws_budgets_budget" "staging" {
  name         = "${var.project_name}-monthly"
  budget_type  = "COST"
  limit_amount = "50"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.staging_ops.arn]
  }
}
