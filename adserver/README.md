# Ad server

## The question it answers

Can one ad server give both ad paths, SSAI (MediaTailor) and SGAI
(vast-2-sgai), the same VAST with the HAND IDs the bridge verified, without
ever opening the video?

## What it does

One endpoint that answers "which ad goes in this break?" with a VAST, in the
shape of contract 2 in [CONTRACTS.md](../CONTRACTS.md):

- the Ad-ID in `UniversalAdId`
- an empty `<Impression>`: nothing is tracked, but MediaTailor needs the element
- two `MediaFile`s: the MP4 (for MediaTailor) and the HLS playlist (for vast-2-sgai)
- the HAND IDs in `<Extension type="hand-id">`, as resolvable URLs

Everything about the ad comes from the `hand_ids.json` the bridge wrote.
**If that file is not there, the answer is an empty VAST**: the bridge did not
trust the mezzanine, so the ad is not served. It is never served without its
IDs.

It does not verify the C2PA (the bridge did), does not query the HAND registry
(the player does) and does not write the playlist.

## Run it

Python 3.9+, standard library only.

```bash
python pipeline/bridge.py media_src/signed_ad.mp4
python adserver/server.py
curl http://127.0.0.1:8080/vast
```

The `MediaFile` URLs only resolve if the packaged ad is served at
`--media-base`. The default matches the repo served on port 8090
(`python -m http.server 8090` from the repo root), with the packaged ad in
`out/ad/`.

To serve more than one ad, give each its own bridge output folder and ask for
it by name:

```bash
python pipeline/bridge.py media_src/signed_ad.mp4 --out out/bridge/legit
curl "http://127.0.0.1:8080/vast?ad=legit"
```

| Option | Default | What it is |
|--------|---------|------------|
| `--port` | `8080` | port, on 127.0.0.1 |
| `--bridge-output` (or `BRIDGE_OUTPUT`) | `out/bridge` | where the bridge output is: a local folder, an `http(s)://` base URL or an `s3://bucket/prefix` |
| `--media-base` (or `AD_MEDIA_BASE`) | `http://localhost:8090/out/ad` | where the packaged ad is served from |

The layout under `--bridge-output` is the same in the three forms:
`hand_ids.json` for the default ad and `<name>/hand_ids.json` for a named one.
The remote forms are for a deployed server, which has no local files:

```bash
python adserver/server.py --bridge-output https://cdn.example/bridge
BRIDGE_OUTPUT=s3://my-bucket/bridge python adserver/server.py   # needs boto3
```

If the remote source can't be reached, the answer is an empty VAST, same as a
missing file.

The `MediaFile` URLs are `<media-base>/<name>/ad.mp4` and
`<media-base>/<name>/index.m3u8`, where `<name>` is the `ad` parameter, or
`default` without one. Both are declared as 1280x720, the size of the packaged
ad, and `Duration` is `HH:MM:SS.mmm`, not rounded to whole seconds.

## Deployed

`lambda_handler.py` is the same ad server as an AWS Lambda behind a Function
URL, for MediaTailor and vast-2-sgai to call. It shares `answer()` with
`server.py`, so both give the same answers. It takes `BRIDGE_OUTPUT` (an
`s3://bucket/prefix`) and `AD_MEDIA_BASE` from the environment.
[infra/](../infra/) creates it and sets both.

## Tests

```bash
python -m unittest discover adserver
```

## What we found

- Running the bridge on the signed mezzanine and asking for that ad returns
  the contract's VAST with the IDs from the C2PA manifest.
- Changing one byte of the mezzanine makes the bridge refuse it
  (`assertion.bmffHash.mismatch`), nothing is written, and the ad server
  answers an empty VAST for that ad.
- **MediaTailor refuses a VAST without `<Impression>`.** It asked the ad
  server at the break, logged `ERROR_ADS_RESPONSE_PARSE` and left the break
  unfilled. Of the variants we tried (with `<Impression>`, without
  `Extensions`, with the MP4 `MediaFile` alone, with a `bitrate` on it) only
  the ones with `<Impression>` were accepted; an empty element is enough.
- With it, MediaTailor picks the MP4 `MediaFile`, ignores the HLS one and the
  `hand-id` extension, and stitches the ad into the break (39 segments,
  78.042 s in a 78.083 s break). The first sessions after a new ad skip it
  (`NEW_CREATIVE`, then `TRANSCODE_IN_PROGRESS`) until MediaTailor has
  transcoded it, about two minutes here.
- It sends no query parameters of its own to the ad server.

## Limitations and next steps

- The `MediaFile` size is fixed at 1280x720. A packaged ad of another size
  needs the constant in `server.py` changed.
- The MediaTailor findings above come from test VASTs served as static files
  to a temporary playback configuration. The deployed ad server has not
  answered MediaTailor with the new VAST yet.
- vast-2-sgai accepted the VAST without `<Impression>` and picked the HLS
  `MediaFile` (checked in the review of this piece). Not checked again with
  the empty `<Impression>`.
- `server.py` listens on localhost only. The public URL MediaTailor needs is
  the same code as a Lambda: see "Deployed" above.
