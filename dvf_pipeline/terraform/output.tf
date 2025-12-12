output "endpoint_url" { value = "http://localhost:4566" }

output "bronze_bucket" { value = aws_s3_bucket.bronze.bucket }
output "silver_bucket" { value = aws_s3_bucket.silver.bucket }
output "gold_bucket" { value = aws_s3_bucket.gold.bucket }

output "silver_queue_url" { value = aws_sqs_queue.silver_queue.id }
output "dlq_url" { value = aws_sqs_queue.dlq.id }

output "sns_topic_arn" { value = aws_sns_topic.pipeline_topic.arn }
