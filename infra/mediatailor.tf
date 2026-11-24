# The SSAI path: a MediaTailor playback configuration with the content stream
# as its origin and the ad server as its ADS.
#
# Neither Terraform provider (aws, awscc) has a playback configuration
# resource, so it is a one-resource CloudFormation stack.

locals {
  mediatailor_ads_url = var.mediatailor_ad == "" ? local.vast_url : "${local.vast_url}?ad=${var.mediatailor_ad}"
  mediatailor_outputs = one(aws_cloudformation_stack.mediatailor[*].outputs)
}

resource "aws_cloudformation_stack" "mediatailor" {
  count = var.enable_mediatailor ? 1 : 0
  name  = "${var.name}-mediatailor"

  template_body = jsonencode({
    Resources = {
      Playback = {
        Type = "AWS::MediaTailor::PlaybackConfiguration"
        Properties = {
          Name = var.name
          # The folder of the content stream: the playback URL adds index.m3u8.
          VideoContentSourceUrl = "${local.media_url}/content"
          AdDecisionServerUrl   = local.mediatailor_ads_url
        }
      }
    }
    Outputs = {
      HlsManifestEndpointPrefix = {
        Value = { "Fn::GetAtt" = ["Playback", "HlsConfiguration.ManifestEndpointPrefix"] }
      }
      SessionInitializationEndpointPrefix = {
        Value = { "Fn::GetAtt" = ["Playback", "SessionInitializationEndpointPrefix"] }
      }
    }
  })
}
