# --- S3 (Bronze) -> Lambda Bronze->Silver
resource "aws_lambda_permission" "allow_bronze_s3" {
  statement_id  = "AllowExecutionFromS3Bronze"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.bronze_to_silver.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.bronze.arn
}

resource "aws_s3_bucket_notification" "bronze_notify" {
  bucket = aws_s3_bucket.bronze.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.bronze_to_silver.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "bronze/"
  }

  depends_on = [aws_lambda_permission.allow_bronze_s3]
}

# --- S3 (Silver) -> SQS
resource "aws_s3_bucket_notification" "silver_notify" {
  bucket = aws_s3_bucket.silver.id

  queue {
    queue_arn     = aws_sqs_queue.silver_queue.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "silver/"
  }
}

# --- SQS -> Lambdas Gold (event source mapping)
resource "aws_lambda_event_source_mapping" "sqs_to_gold_m2" {
  event_source_arn = aws_sqs_queue.silver_queue.arn
  function_name    = aws_lambda_function.gold_price_m2.arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "sqs_to_gold_count" {
  event_source_arn = aws_sqs_queue.silver_queue.arn
  function_name    = aws_lambda_function.gold_count_by_type.arn
  batch_size       = 1
}

# --- DLQ alarm -> SNS (simple: we publish from code; infra just exposes DLQ)
# --- SNS -> Logger subscription
resource "aws_lambda_permission" "allow_sns_invoke_logger" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sns_logger.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.pipeline_topic.arn
}

resource "aws_sns_topic_subscription" "logger_sub" {
  topic_arn = aws_sns_topic.pipeline_topic.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.sns_logger.arn
}
