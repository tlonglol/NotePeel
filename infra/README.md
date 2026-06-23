# NotePeel — AWS deploy (Lambda + Function URL, S3/CloudFront, Neon)

Serverless Path B. No ALB / RDS / NAT / VPC.

## Architecture
```
Internet
  -> CloudFront -> S3 (React build)              [frontend]
  -> Lambda Function URL -> Lambda (FastAPI/Mangum)
        -> Neon Postgres (pooled, over internet)
        -> S3 notepeel-images (presigned PUT/GET) [note images]
EventBridge Scheduler --(rate 5 min, {"warmer":true})--> Lambda  [keep-warm]
```

## One-time / each deploy
```bash
# 0. Fill secrets (rotated keys!) in infra/terraform.tfvars

# 1. Build the Linux Lambda package
cd backend && ./build.sh && cd ..

# 2. (optional) Warn if bucket names are globally taken
cd infra && ./preflight.sh && cd ..

# 3. Provision
cd infra
terraform init
terraform validate
terraform plan -out tfplan      # review: should be all create, no ALB/RDS/NAT
terraform apply tfplan

# 4. Create DB tables in Neon (one-off)
cd ../backend && DATABASE_URL="<neon-pooled-url>" python -m scripts.migrate

# 5. Build + publish frontend
cd ../frontend
VITE_API_URL="$(terraform -chdir=../infra output -raw function_url)" npm run build
aws s3 sync dist/ "s3://$(terraform -chdir=../infra output -raw frontend_bucket)" --delete
aws cloudfront create-invalidation --distribution-id <id> --paths '/*'
```

After first apply, set `allowed_origin` in terraform.tfvars to the `cloudfront_domain`
output and re-apply so CORS is locked down.

## Existing R2 images
New uploads work immediately. To keep OLD notes' images rendering, copy them once:
`rclone copy r2:notepeel-images s3:notepeel-images` (or `aws s3 cp` from a local sync).
