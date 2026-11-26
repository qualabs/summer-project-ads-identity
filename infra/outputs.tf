output "bucket" {
  description = "The bucket upload.sh fills."
  value       = aws_s3_bucket.media.bucket
}

output "distribution_id" {
  description = "The CloudFront distribution upload.sh invalidates."
  value       = aws_cloudfront_distribution.media.id
}

output "media_url" {
  description = "Base URL of everything published."
  value       = local.media_url
}

output "content_url" {
  description = "The content stream, with the break still as colour bars."
  value       = "${local.media_url}/content/index.m3u8"
}

output "ad_url" {
  description = "The packaged ad. The ad server's --media-base / AD_MEDIA_BASE."
  value       = "${local.media_url}/ad"
}

output "vast_url" {
  description = "The ad server. Add ?ad=legit or ?ad=tampered for a named ad."
  value       = local.vast_url
}

# The player on a stream that is not in its built-in list, or before
# upload.sh gave it the URL of the stitched one: each link carries its ?src=.
output "player_links" {
  description = "The demo player on each stream."
  value = { for label, src in {
    content       = "${local.media_url}/content/index.m3u8"
    ad_legit      = "${local.media_url}/ad/legit/index.m3u8"
    ad_tampered   = "${local.media_url}/ad/tampered/index.m3u8"
    ssai_stitched = var.enable_mediatailor ? "${local.mediatailor_outputs["HlsManifestEndpointPrefix"]}index.m3u8" : null
  } : label => "${local.media_url}/player/index.html?src=${urlencode(src)}" if src != null }
}

output "ssai_url" {
  description = "The content stream with the ad stitched by MediaTailor (null without MediaTailor)."
  value       = var.enable_mediatailor ? "${local.mediatailor_outputs["HlsManifestEndpointPrefix"]}index.m3u8" : null
}

output "ssai_session_url" {
  description = "MediaTailor's session initialization prefix, for client-side reporting (null without MediaTailor)."
  value       = var.enable_mediatailor ? local.mediatailor_outputs["SessionInitializationEndpointPrefix"] : null
}
