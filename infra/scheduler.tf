# Keep-warm: invoke the Lambda every 5 minutes with {"warmer": true}.
# The handler short-circuits this event before invoking the FastAPI app.
resource "aws_scheduler_schedule" "warmer" {
  name = "${var.project}-warmer"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(5 minutes)"

  target {
    arn      = aws_lambda_function.api.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ warmer = true })
  }
}
