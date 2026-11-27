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
  description = "The GitHub repository whose workflows assume the roles, as owner/name. Only for the roles' descriptions: what AWS checks is subject_prefix."
  type        = string
  default     = "qualabs/summer-project-ads-identity"

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.repository))
    error_message = "owner/name, as in the repository's URL."
  }
}

variable "subject_prefix" {
  description = "How GitHub names this repository in the `sub` of its OIDC tokens. Read it with `gh api repos/<owner>/<name>/actions/oidc/customization/sub` (sub_claim_prefix). With immutable subjects it carries the owner's and the repository's ids, so a repository that takes over the name later does not match."
  type        = string
  default     = "repo:qualabs@29763741/summer-project-ads-identity@1455285815"

  validation {
    condition     = startswith(var.subject_prefix, "repo:")
    error_message = "The sub_claim_prefix as GitHub prints it: it starts with repo:."
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
