# Route 53 hosted zone for the custom domain.
# PHASE 1: apply this, then set Namecheap's nameservers to the `nameservers`
# output below. Once delegation propagates, PHASE 2 (ACM cert + CloudFront
# alias + alias records) can validate via DNS.
resource "aws_route53_zone" "main" {
  name = var.domain_name
}
