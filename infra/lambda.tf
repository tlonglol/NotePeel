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

  # NOTE: CORS is handled by FastAPI's CORSMiddleware (backend/main.py), which
  # also covers local dev. Do NOT configure a `cors {}` block here too — both
  # layers add an Access-Control-Allow-Origin header, producing a duplicate
  # "*, *" value that browsers reject. To lock CORS down later, change
  # allow_origins in CORSMiddleware to the CloudFront domain.
}

# Required for a NONE-auth Function URL to be publicly invokable. Terraform does
# not add this automatically (the AWS console does), so without it every request
# to the Function URL returns 403 Forbidden.
resource "aws_lambda_permission" "function_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
