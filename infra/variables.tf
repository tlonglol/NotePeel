variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "notepeel"
}

variable "images_bucket_name" {
  type        = string
  default     = "notepeel-images"
  description = "S3 bucket for note images. Globally unique across all of S3."
}

variable "frontend_bucket_name" {
  type        = string
  default     = "notepeel-frontend"
  description = "S3 bucket for the built React app. Globally unique across all of S3."
}

variable "lambda_memory_mb" {
  type    = number
  default = 1536
}

variable "lambda_timeout_s" {
  type    = number
  default = 300
}

variable "allowed_origin" {
  type        = string
  description = "Frontend origin for CORS, e.g. https://dxxxx.cloudfront.net. Set after first apply once the CloudFront domain exists, or pass the custom domain."
  default     = "*"
}

# ---- Secrets: provide via terraform.tfvars (gitignored) or TF_VAR_*; never commit ----
variable "database_url" {
  type        = string
  sensitive   = true
  description = "Neon POOLED connection string (the -pooler host)."
}

variable "gemini_api_key" {
  type      = string
  sensitive = true
}

variable "google_client_id" {
  type = string
}

variable "cf_account_id" {
  type      = string
  sensitive = true
}

variable "cf_api_token" {
  type      = string
  sensitive = true
}
