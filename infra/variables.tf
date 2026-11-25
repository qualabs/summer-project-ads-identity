variable "region" {
  description = "AWS region. It must be one where MediaTailor is available."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Prefix of every resource name."
  type        = string
  default     = "ads-identity-demo"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,32}$", var.name))
    error_message = "Lowercase letters, digits and hyphens, at most 32 characters (it is part of the bucket name)."
  }
}

variable "enable_mediatailor" {
  description = "Create the MediaTailor playback configuration (the SSAI path). The SGAI path does not need it."
  type        = bool
  default     = true
}

variable "mediatailor_ad" {
  description = "Which ad MediaTailor asks the ad server for: a name under out/ad/ (legit, tampered). Empty asks for the default ad."
  type        = string
  default     = ""

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{0,64}$", var.mediatailor_ad))
    error_message = "An ad name as the ad server accepts it: letters, digits, _ and -."
  }
}
