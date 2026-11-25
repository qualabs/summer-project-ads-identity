#!/usr/bin/env bash
#
# upload.sh
#
# Copies what the pipeline wrote in out/ (and the player) to the bucket that
# Terraform created, then invalidates CloudFront. Run it after `terraform
# apply`, and again every time out/ changes.
#
#   infra/upload.sh
#
# What is not in out/ is removed from the bucket too. That matters for
# bridge/: a missing hand_ids.json means "do not serve this ad", so an ad the
# bridge refused locally stops being served once this runs.
#
# Needs the AWS CLI and terraform, with the same credentials as the apply.

set -euo pipefail

infra="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$infra")"

bucket="$(terraform -chdir="$infra" output -raw bucket)"
distribution="$(terraform -chdir="$infra" output -raw distribution_id)"

# sync <local folder> <prefix> <pattern> <content type> [more sync options]
# One call per file type: the AWS CLI guesses the Content-Type from the
# extension and gets .ts wrong.
sync() {
  local from="$1" prefix="$2" pattern="$3" type="$4"
  shift 4
  aws s3 sync "$from" "s3://$bucket/$prefix" --delete --only-show-errors \
    --exclude "*" --include "$pattern" --content-type "$type" "$@"
}

hls() {
  sync "$1" "$2" "*.m3u8" "application/vnd.apple.mpegurl"
  sync "$1" "$2" "*.ts" "video/mp2t"
  sync "$1" "$2" "*.mp4" "video/mp4"
}

if [ -d "$root/out/content" ]; then
  echo "content stream  out/content -> s3://$bucket/content"
  hls "$root/out/content" content
else
  echo "no out/content: run content/make_stream.py (nothing uploaded for it)" >&2
fi

if [ -d "$root/out/ad" ]; then
  echo "packaged ad     out/ad -> s3://$bucket/ad"
  hls "$root/out/ad" ad
else
  echo "no out/ad: run ad-packaging/package_ad.py (nothing uploaded for it)" >&2
fi

# Only the hand_ids.json files: all the ad server reads.
if [ -d "$root/out/bridge" ]; then
  echo "bridge output   out/bridge -> s3://$bucket/bridge"
  sync "$root/out/bridge" bridge "*hand_ids.json" "application/json"
else
  echo "no out/bridge: removing s3://$bucket/bridge, so no ad is served" >&2
  aws s3 rm "s3://$bucket/bridge" --recursive --only-show-errors
fi

echo "player          player -> s3://$bucket/player"
sync "$root/player" player "*.html" "text/html; charset=utf-8" --exclude "test/*"
sync "$root/player" player "*.js" "text/javascript; charset=utf-8" --exclude "test/*"
aws s3 cp "$root/ids.json" "s3://$bucket/ids.json" --only-show-errors --content-type "application/json"

echo "invalidating CloudFront $distribution"
aws cloudfront create-invalidation --distribution-id "$distribution" --paths "/*" \
  --query "Invalidation.Id" --output text

echo
echo "content  $(terraform -chdir="$infra" output -raw content_url)"
echo "vast     $(terraform -chdir="$infra" output -raw vast_url)"
echo "player   terraform -chdir=infra output player_links"
