resource "aws_sqs_queue" "dlq" {
  name                       = "${var.project}-silver-dlq"
  visibility_timeout_seconds = 600
  message_retention_seconds  = 1209600
}

resource "aws_sqs_queue" "silver_queue" {
  name                       = "${var.project}-silver-queue"
  visibility_timeout_seconds = 600
  message_retention_seconds  = 1209600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}
