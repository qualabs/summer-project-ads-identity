# Copy to terraform.tfvars (git-ignored) and fill in.
source_dir = "../../../vast-2-sgai"                                       # your clone of montevideo-tech/vast-2-sgai, after npm ci
vast_url   = "https://<function-url-id>.lambda-url.us-east-1.on.aws/vast" # terraform -chdir=infra output -raw vast_url
# origin_whitelist = "<distribution>.cloudfront.net"              # empty: any origin
