variable "region" {
  description = "AWS region, the same as infra/."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Prefix of infra/'s resource names (its `name` variable): the deploy role may manage the IAM roles that start with it."
  type        = string
  default     = "ads-identity-demo"
}

variable "repository" {
  description = "The GitHub repository whose workflows may assume the roles, as owner/name."
  type        = string
  default     = "qualabs/summer-project-ads-identity"

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.repository))
    error_message = "owner/name, as in the repository's URL."
  }
}

variable "role_prefix" {
  description = "Prefix of the two roles created here. It must not start with `name`, or the deploy role could change its own permissions."
  type        = string
  default     = "ads-identity-ci"

  validation {
    condition     = !startswith(var.role_prefix, var.name)
    error_message = "role_prefix must not start with name: the deploy role may manage every role that starts with name."
  }
}
