# Ad server

## The question it answers

Can one ad server give both ad paths, SSAI (MediaTailor) and SGAI
(vast-2-sgai), the same VAST with the HAND IDs the bridge verified, without
ever opening the video?

## What it does

One endpoint that answers "which ad goes in this break?" with a VAST, in the
shape of contract 2 in [CONTRACTS.md](../CONTRACTS.md):

- the Ad-ID in `UniversalAdId`
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
| `--media-base` (or `AD_MEDIA_BASE`) | `http://localhost:8000/ads` | where the packaged ad is served from |

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
`default` without one.

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

## Limitations and next steps

- The `MediaFile` URLs point to a packaged ad that does not exist yet; the
  folder layout above is this server's assumption until that piece is built.
- The VAST carries exactly what contract 2 shows. VAST 4.2 also asks for an
  `<Impression>` in every `InLine`; whether MediaTailor or vast-2-sgai reject
  the VAST without it is still to be tested with each tool.
- Not tested yet against MediaTailor or vast-2-sgai (which `MediaFile` each
  one picks, and which query parameters they send).
- It listens on localhost only. MediaTailor needs a public URL: that
  deployment is part of the SSAI path.
