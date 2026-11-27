# What GitHub Actions needs to reach the account without stored keys: GitHub
# as an OIDC identity provider, and two roles its workflows assume.
#
#   <role_prefix>-plan    read-only, for pull requests (terraform plan)
#   <role_prefix>-deploy  what infra/ needs to apply, only from main
#
# Applied by hand, by someone who may manage IAM. The workflows never apply
# this configuration: a deploy must not be able to change its own permissions.

data "aws_caller_identity" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  github  = "token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.github}"
  client_id_list = ["sts.amazonaws.com"]
}

# Who may assume each role: a workflow of this repository, and only for the
# given `sub` (what GitHub says the run is: a pull request, or a ref).
data "aws_iam_policy_document" "assume" {
  for_each = {
    plan   = "repo:${var.repository}:pull_request"
    deploy = "repo:${var.repository}:ref:refs/heads/main"
  }

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github}:sub"
      values   = [each.value]
    }
  }
}

# Pull requests: read the account and the state, change nothing. The plan
# runs with -lock=false, so it does not write the lock file either.
resource "aws_iam_role" "plan" {
  name               = "${var.role_prefix}-plan"
  description        = "GitHub Actions, pull requests of ${var.repository}: terraform plan of infra/"
  assume_role_policy = data.aws_iam_policy_document.assume["plan"].json
}

resource "aws_iam_role_policy_attachment" "plan_read_only" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# main: apply infra/ and upload the player.
resource "aws_iam_role" "deploy" {
  name               = "${var.role_prefix}-deploy"
  description        = "GitHub Actions, main of ${var.repository}: terraform apply of infra/ and the player upload"
  assume_role_policy = data.aws_iam_policy_document.assume["deploy"].json
}

data "aws_iam_policy_document" "deploy" {
  # The services infra/ creates resources in, plus the state and the uploads.
  statement {
    sid = "Services"
    actions = [
      "s3:*",
      "cloudfront:*",
      "lambda:*",
      "logs:*",
      "cloudformation:*",
      "mediatailor:*",
    ]
    resources = ["*"]
  }

  # The ad server's execution role (infra/README.md, "What we found"). Only
  # roles named <name>-*: not the two roles of this file.
  statement {
    sid = "ExecutionRoles"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy",
      "iam:GetRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:aws:iam::${local.account}:role/${var.name}-*"]
  }

  statement {
    sid       = "PassExecutionRoleToLambda"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account}:role/${var.name}-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
