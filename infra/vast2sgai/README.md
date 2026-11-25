# vast-2-sgai on AWS

## The question it answers

Can the SGAI path use its own vast-2-sgai, in our AWS account, without
changing its code and without Docker?

vast-2-sgai ([montevideo-tech/vast-2-sgai](https://github.com/montevideo-tech/vast-2-sgai))
turns the ad server's VAST into the asset list of an HLS Interstitial: it is
what `X-ASSET-LIST` in the content playlist points to. The public instance we
used before no longer resolves, so we run our own.

## What it creates

A separate Terraform configuration, with its own local state. It does not
touch what `infra/` created, and it can be applied and destroyed on its own.

| Resource | Why |
|---|---|
| A Lambda (Node.js) with the clone of vast-2-sgai as its code | The server, unchanged |
| The [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) layer | vast-2-sgai is an Express server (`node src/server.js`, port 3000); the adapter forwards each request to it |
| A one-file layer with `start.sh` | The command the adapter runs. Kept apart so the function zip is the clone as it is |
| A public Function URL and its two permissions | The player calls it from the browser |
| An IAM role that may only write its log, and the log group | |

Everything carries the `Project` tag of `infra/`, plus `Component = vast2sgai`.

Configuration, as environment variables (see vast-2-sgai's `.env.example`):

| Variable | Value | Why |
|---|---|---|
| `VAST_WHITELIST` | the host of `vast_url` | Only our ad server's VAST is accepted |
| `ORIGIN_WHITELIST` | `origin_whitelist`, empty by default | Empty accepts any origin (the player locally or on CloudFront) |
| `API_DISABLE_SIGN` | `true` | We pass `vasturl`, not a signed JWT |

The clone's `.env` is not uploaded: its values are examples.

## Run it

Needs Terraform 1.5+, Node.js and npm, and AWS credentials that may create
Lambda and IAM resources. No Docker.

1. A clone of vast-2-sgai with its dependencies. Checked against commit
   `3c6c41a`.

   ```bash
   git clone https://github.com/montevideo-tech/vast-2-sgai
   cd vast-2-sgai && npm ci
   ```

2. The variables: copy `example.tfvars` to `terraform.tfvars` and set
   `source_dir` (the clone) and `vast_url` (`terraform -chdir=infra output -raw vast_url`).

3. Apply:

   ```bash
   cd infra/vast2sgai
   terraform init
   terraform apply
   ```

4. Check it with the `asset_list_url` output:

   ```bash
   curl "$(terraform output -raw asset_list_url)"
   ```

   It should answer `{"ASSETS":[{"URI":".../ad/legit/index.m3u8","DURATION":78.047,...}]}`.

The SGAI interstitial in the content playlist then uses that URL, with the ad
it wants (`?ad=legit`, `?ad=tampered`) inside `vasturl`:

```
X-ASSET-LIST="<url>api/asset-list?vasturl=<the VAST URL, percent-encoded>"
```

Remove it:

```bash
terraform destroy
```

## Decisions

- **Lambda, not ECS.** vast-2-sgai's own `infra/` runs it on ECS Fargate behind
  a load balancer, with a VPC, a certificate and a domain. For a demo that is
  more pieces and a fixed cost. A Lambda costs per request and is the same
  pattern as the ad server.
- **A zip, not a container image.** Its dependencies are all JavaScript. The
  `Dockerfile` installs system libraries for `canvas`, but nothing in
  `package.json` or `src/` uses it.
- **Its own state.** `infra/`'s state is on the machine of whoever applied it.
  A separate configuration can be applied from another machine without
  recreating the bucket, CloudFront or the ad server. To merge them later,
  move both states to S3 first.

## What we found

- `terraform validate` passes (Terraform 1.17.2, `aws` provider 6.74.0,
  `archive` 2.8.1).
- **Run locally with the same environment** (`node src/server.js`), against the
  deployed ad server: `/api/asset-list` returns our `index.m3u8` with
  `DURATION` 78.047; a VAST from another host gets `403`; `/api/sign` answers
  `401` (disabled); every answer has `Access-Control-Allow-Origin: *`.
- The zip is about 8.5 MB, with no `.env`.
- `start.sh` has to reach Lambda executable and with LF line ends. An inline
  `source` block in `archive_file` gets no file mode, so it is a file, zipped
  with `output_file_mode = "0755"`, and `.gitattributes` keeps it LF on a
  Windows checkout.
- **Not applied yet.** Nothing here has run on Lambda: the adapter, the layer
  and the Function URL are unchecked.
- The asset list carries vast-2-sgai's own `X-AD-CREATIVE-SIGNALING` (tracking
  slots, no identifiers). The player reads the HAND IDs from the ad's playlist,
  as in the other paths (contract 3).
