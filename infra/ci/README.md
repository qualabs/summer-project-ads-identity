# infra/ci

How does GitHub Actions reach the AWS account to plan and deploy `infra/`,
without an access key stored in the repository?

## What it creates

A separate Terraform configuration, with its own state
(`s3://ads-identity-tfstate/ci/terraform.tfstate`).

| Resource | Why |
|---|---|
| An IAM OIDC identity provider for `token.actions.githubusercontent.com` | AWS trusts the short-lived token GitHub gives each workflow run. One per account |
| Role `ads-identity-ci-plan` | Pull requests: `ReadOnlyAccess`, enough for `terraform plan`. Only a `pull_request` run of this repository may assume it |
| Role `ads-identity-ci-deploy` | Merges to main: what `infra/` needs to apply and `upload.sh code` to upload. Only a run on `refs/heads/main` of this repository may assume it |

The workflows that use them are `.github/workflows/plan.yml` and
`deploy.yml`. What they do is in [`../README.md`](../README.md), "Deploy on
merge".

## Run it

Once, by hand, by someone who may create an OIDC provider and IAM roles in the
account (the deploy workflow never applies this folder):

```bash
cd infra/ci
terraform init
terraform apply
```

Then give GitHub the two role ARNs, as repository **variables** (Settings →
Secrets and variables → Actions → Variables). They are not secrets: a role ARN
only says which role, and only this repository's workflows may assume it.

```bash
gh variable set AWS_PLAN_ROLE_ARN --body "$(terraform -chdir=infra/ci output -raw plan_role_arn)"
gh variable set AWS_DEPLOY_ROLE_ARN --body "$(terraform -chdir=infra/ci output -raw deploy_role_arn)"
```

If the account already has an OIDC provider for GitHub, import it instead of
creating a second one (AWS refuses it):

```bash
terraform import aws_iam_openid_connect_provider.github \
  arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com
```

## Decisions

- **No stored keys.** A workflow run asks GitHub for a token that says which
  repository and which ref it runs for; AWS exchanges it for credentials that
  last one hour. There is nothing to rotate or to leak.
- **Two roles.** A pull request runs the Terraform of its own branch, before
  anyone reviewed it, so it gets a role that can only read. The role that can
  change things is tied to main.
- **The roles are not named `ads-identity-demo-*`.** The deploy role may
  manage the IAM roles with that prefix (the ad server's execution role). With
  another prefix it cannot change its own permissions. `variables.tf` refuses
  a `role_prefix` that starts with `name`.
- **Not applied by the workflows.** A merge must not be able to widen what the
  next merge may do. A change here is a manual apply.
- **The deploy role is scoped by service**, not `PowerUserAccess`: S3,
  CloudFront, Lambda, CloudWatch Logs, CloudFormation and MediaTailor, plus the
  IAM actions on `role/ads-identity-demo-*` that `infra/README.md` lists. A new
  kind of resource in `infra/` needs its service added here first.
- **`infra/vast2sgai/` is not covered.** Its deploy needs a clone of
  vast-2-sgai with its dependencies; it stays manual.

## What we found

- `terraform validate` passes (Terraform 1.17.2).
- **Not applied yet**, so nothing below the syntax is confirmed: that the
  account lets us create the OIDC provider, that the deploy role's policy is
  enough for an apply of `infra/`, and that `ReadOnlyAccess` is enough for its
  plan.
- When this was written the account had no OIDC provider for GitHub.
