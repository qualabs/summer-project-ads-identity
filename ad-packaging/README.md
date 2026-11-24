# Ad packaging: legit and tampered versions

**Question:** can we package the signed mezzanine as an HLS ad whose own
playlist carries the HAND IDs from the C2PA, and produce a tampered version the
player has to flag?

## What it does

`package_ad.py` runs the bridge on the signed mezzanine, encodes it once (a
720p MP4, then cut into HLS segments without re-encoding) and writes two
playlists over the same segments:

| Output (`out/ad/`) | `EXT-X-DATERANGE` |
|---|---|
| `legit/index.m3u8` + `seg_*.ts` | SVTA2053, copied from the bridge's `svta2053.json` (`daterange_attributes` + `ID` + `START-DATE`), as in CONTRACTS.md contract 3 |
| `legit/ad.mp4` | The same encode as one MP4, for MediaTailor (SSAI) |
| `tampered/index.m3u8` (points to `../legit/seg_*.ts`) | Same, with one HAND ID changed (`--tamper`, default `type04`): what someone on the path would do |
| `tampered/ad.mp4` | A copy of `legit/ad.mp4` |
| `ad.json` | What went into each playlist |

The bridge output (`hand_ids.json`, `svta2053.json`) goes to `out/bridge/`, as
the other pieces expect by default, and also to `out/bridge/legit/` and
`out/bridge/tampered/`.

## Where the files have to be

Nothing here calls the ad server: MediaTailor (SSAI) and vast-2-sgai (SGAI)
do. The ad server answers them with a VAST whose `MediaFile` URLs follow a
fixed pattern, and they then fetch those URLs:

```
<media-base>/<name>/ad.mp4        MediaTailor stitches this
<media-base>/<name>/index.m3u8    vast-2-sgai hands this to the player
```

So `out/ad/` is laid out in that pattern, one folder per ad name (`legit`,
`tampered`), and served at `<media-base>`. The ad server also needs the bridge
output under that name (`out/bridge/<name>/hand_ids.json`), or it answers an
empty VAST: hence the copies in `out/bridge/legit/` and `out/bridge/tampered/`.
Both carry the legit IDs: the attack changes the playlist, not the VAST.

To check that each name resolves (with `out/ad/` served on port 8090):

```bash
python adserver/server.py --media-base http://localhost:8090/out/ad
curl "http://127.0.0.1:8080/vast?ad=legit"
```

The other tampering case, a mezzanine without a valid signature, never gets
packaged: the bridge refuses it, and `package_ad.py` exits with code 2 and
removes `out/ad/` and the bridge output (`out/bridge/` and its `legit/` and
`tampered/` folders), so nothing servable is left behind: the ad server
answers an empty VAST.

## How to run

Needs `c2patool`, `ffmpeg` and `ffprobe` on the PATH. The mezzanine stays
outside git (`media_src/` or anywhere else).

```bash
python ad-packaging/package_ad.py media_src/signed_ad.mp4
python ad-packaging/package_ad.py media_src/signed_ad.mp4 --tamper type02
```

Check what a playlist carries:

```bash
python pipeline/svta2053.py <base64 of X-AD-CREATIVE-SIGNALING>
```

## What we found

- The bridge has to run on the mezzanine, before the encode: the HLS segments
  are a re-encode, so the mezzanine's signature does not cover them.
- One encode serves both versions: only the playlist differs, which is also
  the realistic attack (the playlist is text and is not signed).
- A changed `type04` is caught by the permission check (the HAND registry says
  who produced the Type 02). A changed ID of any type is caught by the
  signature check (Phase 6), which compares the playlist with the signed
  manifest.
- `EXT-X-PROGRAM-DATE-TIME` is fixed (`2026-01-01T00:00:00.000Z`), and
  `START-DATE` is the same instant: in SGAI the DATERANGE is relative to the
  ad's own playlist.
- Segments are MPEG-TS, 4 s, 720p. Per-segment C2PA would need fMP4/CMAF; the
  agreed signature proof is a remote manifest (contract 4), so TS is enough.
