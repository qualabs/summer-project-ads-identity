terraform {
  required_version = ">= 1.10" # use_lockfile in the S3 backend

  # Same bucket as infra/ and infra/vast2sgai/, another key (infra/README.md).
  backend "s3" {
    bucket       = "ads-identity-tfstate"
    key          = "ci/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.28"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.name
      Component = "ci"
    }
  }
}
