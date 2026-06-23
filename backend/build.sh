#!/usr/bin/env bash
# Build the Lambda deployment package (Linux x86_64 wheels + app code) into ./build.
# Terraform (infra/lambda.tf) zips this directory.
set -euo pipefail

cd "$(dirname "$0")"
BUILD_DIR="build"

echo "🧹 Cleaning $BUILD_DIR"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

echo "📦 Installing Linux wheels"
# manylinux wheels so native deps (Pillow, psycopg2-binary, pydantic-core,
# cryptography, pillow-heif) run on the Lambda runtime, not macOS.
pip install \
  -r requirements.txt \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --target "$BUILD_DIR"

echo "📂 Copying application code"
cp lambda_handler.py "$BUILD_DIR"/
cp main.py "$BUILD_DIR"/
cp ocr_service.py "$BUILD_DIR"/
cp -r app "$BUILD_DIR"/
cp -r scripts "$BUILD_DIR"/

# Trim test/cache noise to keep the zip lean.
find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true

echo "✅ Build complete. Size: $(du -sh "$BUILD_DIR" | cut -f1)"
