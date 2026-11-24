# summer-project-ads-identity

Proof of concept: carry HAND talent IDs from a C2PA-signed ad, through the ad
chain, to the player, and let the player verify them. Two ad paths are built in
parallel and share everything else:

- **SSAI** with AWS MediaTailor
- **SGAI** with vast-2-sgai (HLS Interstitials)

## Layout

- `pipeline/bridge.py` — verifies the C2PA of the mezzanine, extracts the HAND
  IDs, writes `out/bridge/hand_ids.json` and `out/bridge/svta2053.json`
- `pipeline/extract_hand.py` — the C2PA read and validation used by the bridge
- `pipeline/svta2053.py` — SVTA2053 payload and `EXT-X-DATERANGE` line
- `adserver/` — the ad server: `GET /vast` builds the VAST of contract 2 from
  the bridge's `hand_ids.json` (see its README)
- `content/` — the content stream: `make_stream.py` packages the programme to
  HLS VOD in `out/content/`, with the ad break marked by SCTE-35 `0x34`/`0x35`
  in `EXT-X-DATERANGE` (see its README)
- `ids.json` — only what is not in the C2PA manifest (test Ad-ID, SVTA2053 schemes)
- `media_src/`, `out/` — local only, never committed

## Running the bridge

Needs `c2patool` and `ffprobe` on the PATH. Run it on the mezzanine, before
packaging: a re-encode breaks the signature.

```bash
python pipeline/bridge.py media_src/signed_ad.mp4
```

Exit code 2 means the file can't be trusted and nothing was written.

## Contracts between the pieces

The formats shared by the bridge, the ad server, the playlists and the player
are in @CONTRACTS.md. They are common to the SSAI and SGAI paths.

- Don't change a format in CONTRACTS.md unless the user asks for it.
- If a change needs it, say so before making it, and update CONTRACTS.md in the
  same commit.
- The player reads the HAND IDs only from the SVTA2053 `EXT-X-DATERANGE`,
  whichever path the ad came through.
- The ad server builds the VAST from `hand_ids.json`. It never reads the video.
- A missing bridge output means the ad must not be served, not that it is
  served without IDs.

## Rules

- HAND IDs come only from the C2PA manifest. Don't hardcode them in code,
  tests or docs; use placeholders (`10.23/AAAA-…`) in examples.
- Never commit media, real people's data or likenesses, or credentials
  (see CONTRIBUTING.md).
- Code, comments and docs in this repo are in English.
- Build one piece per folder with its own README: the question it answers, how
  to run it, what we found.
