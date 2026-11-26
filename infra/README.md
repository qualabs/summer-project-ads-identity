# Infra: the demo on AWS

## The question it answers

What does the demo need on AWS so that MediaTailor (SSAI) and vast-2-sgai
(SGAI) can reach the content stream, the packaged ad and the ad server, and
can all of it be created and removed with one command?

## What it creates

Terraform, with local state. Nothing here uploads media: `upload.sh` does.

| File | What | Why |
|---|---|---|
| `storage.tf` | One private S3 bucket and one CloudFront distribution in front of it | Publishes `content/`, `ad/`, `player/`, `sgai/` and `ids.json` over HTTPS with `Access-Control-Allow-Origin: *`. `bridge/` is in the same bucket but CloudFront may not read it |
| `adserver.tf` | The ad server as a Lambda (`adserver/lambda_handler.py`) with a public Function URL | The `GET /vast` both paths call. It reads `s3://<bucket>/bridge` and points the `MediaFile`s at `<CloudFront>/ad` |
| `mediatailor.tf` | A MediaTailor playback configuration: origin = the content stream, ADS = the ad server | The SSAI path. Off with `enable_mediatailor = false` |

What goes where in the bucket:

```
content/   out/content     index.m3u8, media.m3u8, seg_*.ts
ad/        out/ad          legit/, tampered/, default/  (ad.mp4, index.m3u8, seg_*.ts)
bridge/    out/bridge      hand_ids.json, legit/hand_ids.json, tampered/hand_ids.json
player/    player/         index.html, player.js, svta2053.js, test/ (playlists)
out/test-media/  out/test-media  content/seg_*.ts, ad/seg_*.ts (synthetic)
sgai/      out/sgai        legit.m3u8, tampered.m3u8 (segments: ../content/)
ids.json   ids.json
```

`ad/` and `bridge/` keep the layout the ad server expects
(`<name>/ad.mp4`, `<name>/index.m3u8`, `<name>/hand_ids.json`).

Not uploaded: `media_src/` (the signed mezzanine never leaves the machine),
`svta2053.json`, `ad.json` and `content.json`.

The player's test playlists point to `../../out/test-media/`, so their
synthetic segments keep that path in the bucket. Write them with
`python3 player/test/make_test_media.py` before `upload.sh`.

**Everything under `content/`, `ad/`, `player/`, `sgai/` and `out/test-media/` is public** to anyone with
the URL. Check that the ad may be published before running `upload.sh`.

## Run it

Needs [Terraform](https://developer.hashicorp.com/terraform/install) 1.5+, the
AWS CLI and credentials for an account where you may create S3, CloudFront,
Lambda, IAM, CloudFormation and MediaTailor resources.

```bash
cd infra
terraform init
terraform apply
```

Then write `out/` and copy it:

```bash
python3 ad-packaging/package_ad.py media_src/signed_ad.mp4
python3 content/make_stream.py media_src/tears_of_steel_720p.mov
python3 player/test/make_test_media.py
python3 sgai/make_sgai.py out/content/media.m3u8 \n  --vast2sgai "$(terraform -chdir=infra/vast2sgai output -raw url)" \n  --vast "$(terraform -chdir=infra output -raw vast_url)"
infra/upload.sh
```

`upload.sh` syncs `out/` and the player to the bucket and invalidates
CloudFront. Run it again whenever `out/` changes. What is no longer in `out/`
is removed from the bucket: if the bridge refuses the mezzanine, its
`hand_ids.json` disappears locally and, after `upload.sh`, the deployed ad
server answers an empty VAST.

The URLs are Terraform outputs (`terraform output`):

| Output | What it is |
|---|---|
| `content_url` | The content stream, the break still colour bars |
| `ad_url` | Base of the packaged ad (`/legit/index.m3u8`, `/tampered/ad.mp4`, …) |
| `vast_url` | The ad server; `?ad=legit`, `?ad=tampered` for a named ad |
| `ssai_url` | The content stream with the ad stitched by MediaTailor |
| `player_links` | The player on each of the streams above |

To check the ad server once `upload.sh` ran:

```bash
curl "$(terraform -chdir=infra output -raw vast_url)?ad=legit"
```

Variables (`example.tfvars` shows them; copy it to `terraform.tfvars`):

| Variable | Default | What it is |
|---|---|---|
| `region` | `us-east-1` | Must be a region with MediaTailor |
| `name` | `ads-identity-demo` | Prefix of every resource name; the bucket is `<name>-<account id>` |
| `enable_mediatailor` | `true` | Create the playback configuration |
| `mediatailor_ad` | `""` | The ad MediaTailor asks for (`legit`, `tampered`); empty is the default ad |

Remove everything, the bucket and its contents included:

```bash
terraform destroy
```

## Decisions

- **MediaTailor through CloudFormation.** Neither Terraform provider (`aws`,
  `awscc`) has a playback configuration resource, so `mediatailor.tf` is a
  CloudFormation stack with that one resource, managed by Terraform.
- **The Lambda zip is four files** of `adserver/`, listed in `adserver.tf`. A
  new module there has to be added to that list.
- **One ad per MediaTailor configuration.** The ADS URL is fixed, so switching
  between the legit and the tampered ad is `mediatailor_ad` and an apply. A
  player parameter (`?ad=[player_params.ad]`) would switch per session; not
  done until we see how MediaTailor calls the ad server.
- **`bridge/` is private.** Only the Lambda's role reads it. It has no
  `s3:ListBucket`, so a missing `hand_ids.json` comes back as `AccessDenied`,
  which the ad server already reads as "no such ad".
- **State is local** and git-ignored. Two people applying from two machines
  would create two copies: agree on who applies, or move the state to S3
  first.

## What we found

- `terraform validate` passes (Terraform 1.17.2, `aws` provider 6.74.0).
- **Not applied yet.** `terraform plan` and `apply` have not run against an
  account, so nothing below the syntax is confirmed.
- **`PowerUserAccess` is not enough to apply.** That role has no IAM access,
  and the Lambda needs an execution role: `apply` would create the bucket and
  CloudFront and then fail at `iam:CreateRole`. Whoever applies needs, on
  `role/<name>-*`: `iam:CreateRole`, `iam:DeleteRole`, `iam:GetRole`,
  `iam:TagRole`, `iam:PassRole`, `iam:PutRolePolicy`, `iam:GetRolePolicy`,
  `iam:DeleteRolePolicy`, `iam:ListRolePolicies`,
  `iam:ListAttachedRolePolicies` and `iam:ListInstanceProfilesForRole`. The
  alternative is a role created by the account's administrator plus
  `iam:PassRole` on it, with `adserver.tf` changed to use it.
- The Lambda handler is covered by the ad server's tests (`python3 -m unittest
  discover adserver`), with a made-up Function URL event, and it runs from the
  four packaged files alone. Not checked against AWS.

To check on the first apply:

- that the Function URL answers publicly (the two `aws_lambda_permission`s)
- that MediaTailor accepts the CloudFront folder as its content origin and
  acts on the break (`EXT-X-DATERANGE` in a VOD source: see
  [content/README.md](../content/README.md))
- that MediaTailor picks the MP4 `MediaFile` and accepts the VAST without
  `<Impression>` (see [adserver/README.md](../adserver/README.md))

## Limitations and next steps

- vast-2-sgai is not deployed here but in [vast2sgai/](vast2sgai/README.md),
  a separate configuration with its own state. The SGAI playlists
  ([sgai/](../sgai/README.md)) point at it, so they are written with its URL.
- The player's built-in list covers the SGAI path, the test playlists, the
  content stream and the packaged ad. For the stream MediaTailor stitched, use the
  `player_links` output, or `?src=`.
- CloudFront's default domain, no custom domain or certificate.
- No remote C2PA manifest yet (contract 4). It would be published next to the
  ad, under `ad/<name>/`.
