# Ad packaging: legit and tampered versions

**Question:** can we package the signed mezzanine as an HLS ad whose own
playlist carries the HAND IDs from the C2PA, and produce a tampered version the
player has to flag?

## What it does

`package_ad.py` runs the bridge on the signed mezzanine, encodes it once to HLS
and writes two playlists over the same segments:

| Output (`out/ad/`) | `EXT-X-DATERANGE` |
|---|---|
| `legit/index.m3u8` + `seg_*.ts` | SVTA2053, copied from the bridge's `svta2053.json` (`daterange_attributes` + `ID` + `START-DATE`), as in CONTRACTS.md contract 3 |
| `tampered/index.m3u8` (points to `../legit/seg_*.ts`) | Same, with one HAND ID changed (`--tamper`, default `type04`): what someone on the path would do |
| `ad.json` | What went into each playlist |

The other tampering case, a mezzanine without a valid signature, never gets
packaged: the bridge refuses it, and `package_ad.py` exits with code 2 and
removes `out/ad/` and `out/bridge/`, so nothing servable is left behind.

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
