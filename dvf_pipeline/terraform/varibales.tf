variable "project" {
  type    = string
  default = "dvf"
}

variable "bronze_bucket" {
  type    = string
  default = "dvf-bronze"
}

variable "silver_bucket" {
  type    = string
  default = "dvf-silver"
}

variable "gold_bucket" {
  type    = string
  default = "dvf-gold"
}

variable "lambda_timeout" {
  type    = number
  default = 900
}

variable "lambda_memory" {
  type    = number
  default = 1024
}
