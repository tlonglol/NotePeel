# Zip the Linux-built package produced by backend/build.sh (manylinux wheels + app code).
data "archive_file" "backend" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/build"
  output_path = "${path.module}/build/backend.zip"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project}-api"
  retention_in_days = 14
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project}-api"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_s

  environment {
    variables = {
      DATABASE_URL     = var.database_url # Neon POOLED url
      GEMINI_API_KEY   = var.gemini_api_key
      GOOGLE_CLIENT_ID = var.google_client_id
      CF_ACCOUNT_ID    = var.cf_account_id
      CF_API_TOKEN     = var.cf_api_token
      S3_BUCKET_NAME   = var.images_bucket_name
      S3_REGION        = var.region
      # No S3_ENDPOINT and no S3 keys -> boto3 uses the Lambda IAM role.
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"

  cors {
    allow_origins  = [var.allowed_origin, "http://localhost:5173"]
    allow_methods  = ["*"]
    allow_headers  = ["authorization", "content-type"]
    expose_headers = ["content-type"]
    max_age        = 3600
  }
}
