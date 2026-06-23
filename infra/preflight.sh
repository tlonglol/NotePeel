#!/usr/bin/env bash
# Warns if the desired S3 bucket names are already taken globally.
# S3 names are global; if another account owns one, `terraform apply` fails.
set -uo pipefail

check() {
  local bucket="$1"
  # head-bucket: 200 = you own it, 403 = exists (someone else), 404 = available
  local out
  out=$(aws s3api head-bucket --bucket "$bucket" 2>&1)
  local code=$?
  if [ $code -eq 0 ]; then
    echo "✅ $bucket — already exists in YOUR account (will be reused)."
  elif echo "$out" | grep -qi "403\|Forbidden"; then
    echo "❌ $bucket — GLOBALLY TAKEN by another account. Pick a different name in terraform.tfvars."
  elif echo "$out" | grep -qi "404\|Not Found"; then
    echo "✅ $bucket — available."
  else
    echo "⚠️  $bucket — could not determine (check AWS creds). Raw: $out"
  fi
}

echo "Checking bucket name availability..."
check "${1:-notepeel-images}"
check "${2:-notepeel-frontend}"
