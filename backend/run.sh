#!/bin/bash
# Lambda Web Adapter entrypoint (streaming deploys only; see infra/lambda.tf).
# The adapter proxies the Function URL request to this uvicorn process and
# streams the response body back when AWS_LWA_INVOKE_MODE=response_stream.
exec python -m uvicorn main:app --host 0.0.0.0 --port "${AWS_LWA_PORT:-8000}" --workers 1
