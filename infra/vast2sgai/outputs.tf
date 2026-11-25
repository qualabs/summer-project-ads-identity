output "url" {
  description = "Base URL of vast-2-sgai."
  value       = aws_lambda_function_url.vast2sgai.function_url
}

output "asset_list_url" {
  description = "The asset list for the legit ad: what X-ASSET-LIST in the SGAI interstitial points to."
  value       = "${aws_lambda_function_url.vast2sgai.function_url}api/asset-list?vasturl=${urlencode("${var.vast_url}?ad=legit")}"
}
