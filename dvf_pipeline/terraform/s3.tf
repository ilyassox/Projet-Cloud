resource "aws_s3_bucket" "bronze" { bucket = var.bronze_bucket }
resource "aws_s3_bucket" "silver" { bucket = var.silver_bucket }
resource "aws_s3_bucket" "gold" { bucket = var.gold_bucket }
