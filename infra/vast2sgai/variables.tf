variable "region" {
  description = "AWS region, the same as infra/."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Prefix of every resource name, the same as infra/ (so the Project tag matches)."
  type        = string
  default     = "ads-identity-demo"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,32}$", var.name))
    error_message = "Lowercase letters, digits and hyphens, at most 32 characters."
  }
}

variable "source_dir" {
  description = "Path to a clone of montevideo-tech/vast-2-sgai with its dependencies installed (npm ci)."
  type        = string
}

variable "vast_url" {
  description = "The ad server's VAST URL: `terraform -chdir=infra output -raw vast_url`. Only VASTs from its host are accepted."
  type        = string

  validation {
    condition     = can(regex("^https://[^/]+/", var.vast_url))
    error_message = "An https:// URL, as the vast_url output of infra/ prints it."
  }
}

variable "origin_whitelist" {
  description = "Hosts the player may call vast-2-sgai from, comma-separated (e.g. the CloudFront domain). Empty accepts any origin."
  type        = string
  default     = ""
}

variable "runtime" {
  description = "Lambda Node.js runtime."
  type        = string
  default     = "nodejs22.x"
}

variable "lwa_layer_version" {
  description = "Version of the AWS Lambda Web Adapter layer (LambdaAdapterLayerX86), see github.com/awslabs/aws-lambda-web-adapter."
  type        = number
  default     = 30
}
