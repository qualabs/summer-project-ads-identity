# Player: one player for both ad paths

**Question:** can one player read the HAND IDs of an ad whichever path it came
through, SSAI (MediaTailor stitches it) or SGAI (an HLS Interstitial)?

## What it does

`index.html` plays a stream with hls.js 1.6 and reads every SVTA2053
`EXT-X-DATERANGE` it finds (CONTRACTS.md contract 3):

| Path | Where the DATERANGE is | How the player gets it |
|---|---|---|
| SSAI | The playlist it loads: the ad is stitched into it | `LEVEL_LOADED` of the main player |
| SGAI | The ad's own playlist, inside an interstitial | hls.js plays each interstitial asset in a separate player; we hook it (`INTERSTITIAL_ASSET_PLAYER_CREATED`, then that player's `LEVEL_LOADED`) |

For each ad it shows the Ad-ID and the HAND IDs in a panel, matched by
`scheme` (from `ids.json`, not hardcoded). It accepts both `CLASS` values
(`ad-creative-signaling` and `ad-id-signaling`) and only version 1 payloads
with `identifiers`, so vast-2-sgai's asset list `X-AD-CREATIVE-SIGNALING`
(version 2, tracking) is never mistaken for it.

The permission check (HAND registry) and the signature check (remote C2PA
manifest) plug into `onAd(ad)` in `index.html`; the panel already has a line
for each, marked "not built yet".

- `player.js`: the two paths, calls `onAd(ad)` for each ad found
- `svta2053.js`: decodes the payload and sorts the identifiers by scheme
- `test/`: hand-written playlists with placeholder IDs (`10.23/AAAA-…`)

## How to run

Serve the repository root (the player fetches `../ids.json`):

```bash
python player/test/make_test_media.py        # synthetic segments in out/test-media/
python -m http.server 8090 --bind ::1
```

Open `http://localhost:8090/player/` and pick a source:

| Source | What it tests |
|---|---|
| `test/ssai.m3u8` | Stitched playlist: content, ad with the DATERANGE, content. Uses the `ad-id-signaling` CLASS |
| `test/sgai.m3u8` | Content with an interstitial → `test/asset-list.json` → `test/sgai-ad.m3u8` with the DATERANGE |
| `../out/ad/legit/index.m3u8` | The packaged ad (`ad-packaging/`), loaded on its own |
| `../out/ad/tampered/index.m3u8` | Same ad with a changed HAND ID |

Any other playlist: `http://localhost:8090/player/?src=<url>`.

## What we found

- In SGAI the main player never sees the ad's playlist: the IDs have to be read
  from the interstitial's asset player. The ad's playlist is preloaded, so the
  IDs arrive before the ad starts, in time for a permission check. How early
  depends on hls.js's buffering: in the SGAI test (ad at 8 s) we saw them at
  5 s in one run and at 0.1 s in another.
- hls.js 1.6.15 resolves a relative `URI` in the asset list against the page,
  not against the asset list's URL. vast-2-sgai returns absolute URLs; the test
  asset list uses a path from the server root.
- hls.js turns DATERANGEs into metadata cues only if the media is attached when
  the playlist arrives: attach first, then load.
- During an interstitial, `video.currentTime` counts from 0 (the ad's own clock).
- Not checked yet: what MediaTailor actually writes in the stitched playlist
  (contract 3 leaves the CLASS open for that reason).
