# One private bucket for everything the demo publishes, and one CloudFront
# distribution in front of it. upload.sh fills the bucket from out/:
#
#   content/   the content stream (out/content)       public
#   ad/        the packaged ad (out/ad)               public
#   player/    the demo player, and ids.json next to it  public
#   bridge/    the bridge's hand_ids.json files       only the ad server reads it

data "aws_caller_identity" "current" {}

locals {
  public_prefixes = ["content/*", "ad/*", "player/*", "ids.json"]
  media_url       = "https://${aws_cloudfront_distribution.media.domain_name}"
}

resource "aws_s3_bucket" "media" {
  bucket = "${var.name}-${data.aws_caller_identity.current.account_id}"

  # A proof of concept: `terraform destroy` removes the bucket with what is in
  # it. Everything in it can be written again from out/.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "media" {
  name                              = var.name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

# Adds Access-Control-Allow-Origin: * to every answer. The player may run on
# another origin (localhost, in development) and hls.js fetches with CORS.
data "aws_cloudfront_response_headers_policy" "simple_cors" {
  name = "Managed-SimpleCORS"
}

resource "aws_cloudfront_distribution" "media" {
  enabled     = true
  comment     = var.name
  price_class = "PriceClass_100"

  origin {
    origin_id                = "s3"
    domain_name              = aws_s3_bucket.media.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id
  }

  default_cache_behavior {
    target_origin_id           = "s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.simple_cors.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# CloudFront may read the public prefixes and nothing else: bridge/ is not
# reachable from the internet.
data "aws_iam_policy_document" "media_bucket" {
  statement {
    sid       = "CloudFrontReadsThePublicPrefixes"
    actions   = ["s3:GetObject"]
    resources = [for prefix in local.public_prefixes : "${aws_s3_bucket.media.arn}/${prefix}"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.media.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "media" {
  bucket     = aws_s3_bucket.media.id
  policy     = data.aws_iam_policy_document.media_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.media]
}
