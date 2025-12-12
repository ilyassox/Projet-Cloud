resource "aws_sns_topic" "pipeline_topic" {
  name = "${var.project}-pipeline-topic"
}
