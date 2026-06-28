output "function_url" {
  description = "Backend API base URL. Set this as VITE_API_URL when building the frontend."
  value       = aws_lambda_function_url.api.function_url
}

output "cloudfront_domain" {
  description = "Frontend URL. Use as allowed_origin and the app's public address."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, for cache invalidations."
  value       = aws_cloudfront_distribution.frontend.id
}

output "images_bucket" {
  value = aws_s3_bucket.images.bucket
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "nameservers" {
  description = "Set these as Namecheap's Custom DNS nameservers to delegate the domain to Route 53."
  value       = aws_route53_zone.main.name_servers
}
