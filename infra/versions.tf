terraform {
  required_version = ">= 1.10" # use_lockfile in the S3 backend

  # State in S3, shared by everyone who applies and by CI (infra/README.md).
  # The bucket is created by hand, outside Terraform.
  backend "s3" {
    bucket       = "ads-identity-tfstate"
    key          = "infra/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.28" # aws_lambda_permission.invoked_via_function_url
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project = var.name
    }
  }
}
