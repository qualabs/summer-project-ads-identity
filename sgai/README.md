# SGAI content playlists

## The question it answers

What does the content stream need so that the player inserts the ad itself,
as an HLS Interstitial, through vast-2-sgai?

The content stream (`content/`) marks the break with SCTE-35, which is what
MediaTailor reads. vast-2-sgai reads no SCTE-35 and no playlist: it only turns
a VAST into an asset list. So the SGAI path needs its own tag in the content
playlist, of class `com.apple.hls.interstitial`, at the same place
(`content/README.md`, "What each consumer expects as the break marker").

## What it does

`make_sgai.py` takes the content's media playlist and writes it again with one
interstitial at each break, right after the break's `SCTE35-OUT` tag. One
playlist per ad, because the ad is chosen inside the VAST URL:

```
out/sgai/
  legit.m3u8      X-ASSET-LIST → vast-2-sgai → <ad server>/vast?ad=legit
  tampered.m3u8   X-ASSET-LIST → vast-2-sgai → <ad server>/vast?ad=tampered
```

```
#EXT-X-DATERANGE:ID="break-1",START-DATE="2026-01-01T00:01:00.000Z",DURATION=78.083,SCTE35-OUT=0xFC302C…
#EXT-X-DATERANGE:ID="break-1-sgai",CLASS="com.apple.hls.interstitial",START-DATE="2026-01-01T00:01:00.000Z",DURATION=78.083,X-ASSET-LIST="<vast-2-sgai>/api/asset-list?vasturl=<ad server>%2Fvast%3Fad%3Dlegit",X-RESUME-OFFSET=78.083
```

- `START-DATE` and `DURATION` are the break's, copied from its tag.
- `X-RESUME-OFFSET` is the break's duration (78.083 s), not the ad's
  (78.047 s): after the ad the player resumes past the colour bars, with no
  bars left on screen.
- `vasturl` is percent-encoded, so `?ad=` belongs to the VAST URL and not to
  vast-2-sgai's.
- Everything else is the content playlist as it is, SCTE-35 tags included. The
  segments are the content's: by default the playlist refers to them as
  `../content/seg_….ts`, so it goes in `sgai/`, next to `content/`, on
  CloudFront. `infra/upload.sh` uploads `out/sgai/` there, and the player's
  first two buttons open it.
- No HAND IDs here (contract 3 in [CONTRACTS.md](../CONTRACTS.md)). They are in
  the ad's own playlist, which the asset list points to.

The two playlists are separate files instead of a second tag in
`content/media.m3u8` because MediaTailor passes `EXT-X-DATERANGE` through: an
interstitial in the content playlist would also show up in the SSAI path.

## Run it

Python 3.9+, no other dependency.

```bash
python sgai/make_sgai.py <content media.m3u8, path or URL> \
  --vast2sgai "$(terraform -chdir=infra/vast2sgai output -raw url)" \
  --vast "$(terraform -chdir=infra output -raw vast_url)"
```

| Option | Default | What it is |
|--------|---------|------------|
| `--vast2sgai` | (required) | vast-2-sgai's base URL |
| `--vast` | (required) | the ad server's `/vast` URL, without `?ad=` |
| `--ads` | `legit tampered` | one playlist per ad |
| `--segments` | `../content/` | where the content's segments are, seen from the written playlist. A URL (`https://<cloudfront>/content/`) for a playlist served from somewhere else, such as locally |
| `--out` | `out/sgai` | output folder; only `<ad>.m3u8` is written |

It stops and writes nothing if the playlist has no break with `START-DATE` and
`DURATION`, already has an interstitial, or is a multivariant playlist.

`infra/upload.sh` uploads `out/sgai/` to `sgai/` in the bucket. Then open the
player: "SGAI · legit" and "SGAI · tampered" are its first two buttons.

## Tests

```bash
python -m unittest discover sgai
```

No network and no video: a hand-written content playlist with the break as
`content/make_stream.py` writes it. They check the interstitial's timing and
place, the encoded `vasturl`, that the rest of the playlist is unchanged, the
segment paths, and the inputs it refuses.

## What we found

- With the published content playlist (break of 78.083 s at 60 s), each
  playlist gets one interstitial, `break-1-sgai`, and its `X-ASSET-LIST`
  answers with the asset list of that ad: `ad/legit/index.m3u8` or
  `ad/tampered/index.m3u8`, `DURATION` 78.047.
- **The SGAI path works end to end** on AWS (26 November 2026), in the player
  served by CloudFront (hls.js 1.6.15, Chromium), with both playlists uploaded
  to `content/sgai/` (`--segments ../`):
  - at 60 s the interstitial starts, the asset list comes from vast-2-sgai
    and hls.js plays the ad's playlist from CloudFront;
  - the player reads the SVTA2053 `EXT-X-DATERANGE` from that playlist: the
    Ad-ID and the three HAND IDs for `legit`, and the changed `type04`
    (last group `0000`) for `tampered`;
  - at 138.07 s the interstitial ends and the programme comes back, with no
    colour bars on screen.
- hls.js asks for the asset list a few seconds before the break (at 57.3 s
  when playback started at 57 s), so the ad is ready when the break starts.
- **Where the playlists go on CloudFront.** The bucket policy (`infra/`) let
  CloudFront read only its public prefixes, so in `sgai/` they answered `403`;
  the test above used `content/sgai/`, which `upload.sh` removes on its next
  run (it syncs `content/` with `--delete`). `sgai/*` is now a public prefix
  and `upload.sh` uploads `out/sgai/`; it takes effect with the next
  `terraform apply` of `infra/`.
- From a page served locally, the in-app browser used here got CloudFront's
  answers without `Access-Control-Allow-Origin` (curl, with the same `Origin`,
  gets `*`), so hls.js could not load the content. Served from CloudFront
  itself there is no cross-origin request.

Not verified:

- Safari / native HLS Interstitials.
- What the player shows when the IDs do not match: the permission check and
  the signature check are not built yet (they plug into the player).
