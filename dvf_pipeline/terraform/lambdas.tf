locals {
  build_dir = "${path.module}/build"
}


data "archive_file" "ingest_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/ingest_to_bronze"
  output_path = "${local.build_dir}/ingest_to_bronze.zip"
}

data "archive_file" "b2s_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/bronze_to_silver"
  output_path = "${local.build_dir}/bronze_to_silver.zip"
}

data "archive_file" "gold_m2_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/gold_price_m2"
  output_path = "${local.build_dir}/gold_price_m2.zip"
}

data "archive_file" "gold_count_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/gold_count_by_type"
  output_path = "${local.build_dir}/gold_count_by_type.zip"
}

data "archive_file" "logger_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/sns_logger"
  output_path = "${local.build_dir}/sns_logger.zip"
}

resource "aws_lambda_function" "ingest" {
  function_name    = "${var.project}-ingest-to-bronze"
  role             = aws_iam_role.lambda_role.arn
  handler          = "app.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.ingest_zip.output_path
  source_code_hash = data.archive_file.ingest_zip.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory

  environment {
    variables = {
      BRONZE_BUCKET = var.bronze_bucket
      SNS_TOPIC_ARN = aws_sns_topic.pipeline_topic.arn
    }
  }
}

resource "aws_lambda_function" "bronze_to_silver" {
  function_name    = "${var.project}-bronze-to-silver"
  role             = aws_iam_role.lambda_role.arn
  handler          = "app.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.b2s_zip.output_path
  source_code_hash = data.archive_file.b2s_zip.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = 2048

  environment {
    variables = {
      BRONZE_BUCKET = var.bronze_bucket
      SILVER_BUCKET = var.silver_bucket
      SNS_TOPIC_ARN = aws_sns_topic.pipeline_topic.arn
    }
  }
}

resource "aws_lambda_function" "gold_price_m2" {
  function_name    = "${var.project}-gold-price-m2"
  role             = aws_iam_role.lambda_role.arn
  handler          = "app.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.gold_m2_zip.output_path
  source_code_hash = data.archive_file.gold_m2_zip.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = 2048

  environment {
    variables = {
      SILVER_BUCKET = var.silver_bucket
      GOLD_BUCKET   = var.gold_bucket
      SNS_TOPIC_ARN = aws_sns_topic.pipeline_topic.arn
    }
  }
}

resource "aws_lambda_function" "gold_count_by_type" {
  function_name    = "${var.project}-gold-count-by-type"
  role             = aws_iam_role.lambda_role.arn
  handler          = "app.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.gold_count_zip.output_path
  source_code_hash = data.archive_file.gold_count_zip.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = 2048

  environment {
    variables = {
      SILVER_BUCKET = var.silver_bucket
      GOLD_BUCKET   = var.gold_bucket
      SNS_TOPIC_ARN = aws_sns_topic.pipeline_topic.arn
    }
  }
}

resource "aws_lambda_function" "sns_logger" {
  function_name    = "${var.project}-sns-logger"
  role             = aws_iam_role.lambda_role.arn
  handler          = "app.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.logger_zip.output_path
  source_code_hash = data.archive_file.logger_zip.output_base64sha256
  timeout          = 60
  memory_size      = 256
}
