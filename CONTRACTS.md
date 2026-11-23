# Contracts between the pieces

The demo has two ad paths, SSAI (MediaTailor) and SGAI (vast-2-sgai), built in
parallel. Both use the same bridge, the same ad server, the same content
stream, the same packaged ad and the same player. This file is the format each
piece hands to the next one, so the two paths fit together without either one
building its own copy.

All four are **Frozen**: agreed by both path owners. A change needs both to
agree and is made in the same commit as the code that changes it. Contracts 1
and 3 describe what the code already does; 2 and 4 are agreed designs that are
not built yet.

| # | Contract | Written by | Read by | Status |
|---|----------|------------|---------|--------|
| 1 | Bridge output | `pipeline/bridge.py` | ad server, ad packaging | Frozen (matches the code) |
| 2 | VAST | ad server | MediaTailor, vast-2-sgai | Frozen (agreed, not built yet) |
| 3 | Playlist signal | ad packaging (SGAI), MediaTailor or post-stitch fix-up (SSAI) | player | Frozen (matches the code) |
| 4 | Signature proof | ad packaging | player | Frozen (agreed, not built yet) |

The HAND IDs in the examples are placeholders (`10.23/AAAA-…`). Real IDs come
only from the C2PA manifest of the mezzanine, never from this file.

## 1. Bridge output

`python pipeline/bridge.py <signed mezzanine>` writes two files to `out/bridge/`.
If the C2PA does not validate, it exits with code 2 and removes both files:
**a missing file means "do not serve this ad"**, never "serve it without IDs".

### `hand_ids.json` — for the ad server

```json
{
  "ad_id": "QLAB0000001H",
  "hand": {
    "type01": "10.23/AAAA-AAAA-AAAA-AAAA-0001",
    "type02": "10.23/AAAA-AAAA-AAAA-AAAA-0002",
    "type04": "10.23/AAAA-AAAA-AAAA-AAAA-0004"
  },
  "resolver": "https://doi.org/",
  "source": {
    "file": "signed_ad.mp4",
    "sha256": "<sha256 of the mezzanine>",
    "duration": 78.047,
    "c2pa": {
      "validation_state": "Valid",
      "signer": "C2PA Test Signing Cert",
      "untrusted_cert": true,
      "hand_ids_from": "active manifest"
    },
    "verified_at": "2026-11-20T15:00:25+00:00"
  }
}
```

- `hand.type01` and `hand.type02` are always present. `hand.type04` is present
  only if the manifest carries it. Consumers must not assume it is there.
- IDs are stored bare (`10.23/…`), as the HAND registry does. The resolvable
  form is `resolver + id`.
- `ad_id` is not in the C2PA: it comes from `--ad-id` or `ids.json`.

### `svta2053.json` — for whoever writes the playlist

```json
{
  "class": "urn:svta:advertising-wg:ad-creative-signaling",
  "attribute": "X-AD-CREATIVE-SIGNALING",
  "payload": { "version": 1, "identifiers": [ { "scheme": "…", "value": "…" } ] },
  "base64": "<payload, base64>",
  "daterange_attributes": {
    "CLASS": "urn:svta:advertising-wg:ad-creative-signaling",
    "X-AD-CREATIVE-SIGNALING": "<payload, base64>",
    "DURATION": 78.047
  },
  "note": "<reminder of what the playlist writer adds>",
  "source": { "file": "signed_ad.mp4", "sha256": "<sha256 of the mezzanine>" }
}
```

The playlist writer copies `daterange_attributes` as they are and adds only
`ID` and `START-DATE` (see contract 3). It never rebuilds the payload.

## 2. VAST

One ad server, one endpoint, one VAST for both paths. The ad server builds it
from `hand_ids.json`; it never opens the video file.

```xml
<VAST version="4.2">
  <Ad id="QLAB0000001H">
    <InLine>
      <AdSystem>ads-identity-demo</AdSystem>
      <AdTitle>…</AdTitle>
      <Creatives>
        <Creative>
          <UniversalAdId idRegistry="ad-id.org">QLAB0000001H</UniversalAdId>
          <Linear>
            <Duration>00:01:18</Duration>
            <MediaFiles>
              <MediaFile delivery="progressive" type="video/mp4" …>https://…/ad.mp4</MediaFile>
              <MediaFile delivery="streaming" type="application/x-mpegURL" …>https://…/ad/index.m3u8</MediaFile>
            </MediaFiles>
          </Linear>
        </Creative>
      </Creatives>
      <Extensions>
        <Extension type="hand-id">
          <HandId type="01">https://doi.org/10.23/AAAA-AAAA-AAAA-AAAA-0001</HandId>
          <HandId type="02">https://doi.org/10.23/AAAA-AAAA-AAAA-AAAA-0002</HandId>
          <HandId type="04">https://doi.org/10.23/AAAA-AAAA-AAAA-AAAA-0004</HandId>
        </Extension>
      </Extensions>
    </InLine>
  </Ad>
</VAST>
```

Agreed:

- **Where the HAND IDs go.** In `Extensions`, as `<Extension type="hand-id">`.
- **Which `MediaFile`s.** Both: the MP4 for MediaTailor (it re-encodes the ad)
  and the HLS playlist for vast-2-sgai.
- **ID form inside the VAST.** The resolvable URL (`https://doi.org/10.23/…`),
  same as the SCTE-35 URI UPID.

To test when each path is built: that MediaTailor picks the MP4 and vast-2-sgai
the HLS playlist. This is a check of how the tools behave, not an open
decision.

## 3. Playlist signal

The player reads the HAND IDs from one place in both paths: the SVTA2053
`EXT-X-DATERANGE` of the ad.

```
#EXT-X-DATERANGE:ID="ad-1",CLASS="urn:svta:advertising-wg:ad-creative-signaling",START-DATE="2026-01-01T00:00:00.000Z",DURATION=30.000,X-AD-CREATIVE-SIGNALING="eyJ2ZXJzaW9uIjoxLCJpZGVudGlmaWVycyI6W3sic2NoZW1lIjoidXJuOnNtcHRlOnVsOjA2MEUyQjM0LjAxMDQwMTAxLjAxMjAwOTAwLjAwMDAwMDAwIiwidmFsdWUiOiJRTEFCMDAwMDAwMUgifSx7InNjaGVtZSI6InVybjpoYW5kLWlkOnR5cGUwMSIsInZhbHVlIjoiMTAuMjMvQUFBQS1BQUFBLUFBQUEtQUFBQS0wMDAxIn0seyJzY2hlbWUiOiJ1cm46aGFuZC1pZDp0eXBlMDIiLCJ2YWx1ZSI6IjEwLjIzL0FBQUEtQUFBQS1BQUFBLUFBQUEtMDAwMiJ9LHsic2NoZW1lIjoidXJuOmhhbmQtaWQ6dHlwZTA0IiwidmFsdWUiOiIxMC4yMy9BQUFBLUFBQUEtQUFBQS1BQUFBLTAwMDQifV19"
```

`X-AD-CREATIVE-SIGNALING` decodes (`python pipeline/svta2053.py <base64>`) to:

```json
{
  "version": 1,
  "identifiers": [
    { "scheme": "urn:smpte:ul:060E2B34.01040101.01200900.00000000", "value": "QLAB0000001H" },
    { "scheme": "urn:hand-id:type01", "value": "10.23/AAAA-AAAA-AAAA-AAAA-0001" },
    { "scheme": "urn:hand-id:type02", "value": "10.23/AAAA-AAAA-AAAA-AAAA-0002" },
    { "scheme": "urn:hand-id:type04", "value": "10.23/AAAA-AAAA-AAAA-AAAA-0004" }
  ]
}
```

Rules:

- **Who writes it.** SGAI: the ad's own playlist, written once when the ad is
  packaged; `START-DATE` is that playlist's first `EXT-X-PROGRAM-DATE-TIME`.
  SSAI: MediaTailor if it can carry our identifiers, otherwise a fix-up of ours
  after stitching; `START-DATE` is where the ad landed.
- `ID` is unique within the playlist. It is not the Ad-ID (that is inside the
  payload).
- `EXT-X-PROGRAM-DATE-TIME` is required, also in VOD.
- The player matches identifiers by `scheme`, not by position, and ignores
  schemes it does not know.
- The player accepts both `CLASS` values:
  `urn:svta:advertising-wg:ad-creative-signaling` (normative, what we write)
  and `urn:svta:advertising-wg:ad-id-signaling` (used in the spec's examples;
  what MediaTailor emits is still to be checked).
- The `urn:hand-id:*` schemes are provisional, to be agreed with HAND. They
  live in `ids.json`; nothing else hardcodes them.
- The content's SCTE-35 placement opportunity (0x34 / 0x35) only marks the
  break. It carries no HAND IDs.
- In SGAI the HAND IDs are only in the ad's own playlist, not in the content
  playlist (its interstitial just points to vast-2-sgai) nor in vast-2-sgai's
  asset list. hls.js loads that playlist in a separate player for the
  interstitial, so the player page reads the `EXT-X-DATERANGE` from there.
- vast-2-sgai's asset list has its own `X-AD-CREATIVE-SIGNALING` (version 2,
  tracking only). It is not this signal: the player never reads HAND IDs from it.

## 4. Signature proof

The player has to check that the IDs in the playlist are the ones the producer
signed. It never receives the signed mezzanine, only segments.

Agreed: a **remote C2PA manifest** in both paths. The manifest is published
next to the packaged ad, the VAST points to it, and the player downloads it,
verifies the signature and compares its `org.hand-id.identity` assertion with
the identifiers from contract 3.

Why remote and not per-segment C2PA: MediaTailor re-encodes the ad, so a
signature embedded in the media does not survive the SSAI path. A remote
manifest gives the player one code path for both.

To settle while building Phase 6:

- Where the manifest URL goes so it reaches the player: the player doesn't see
  the VAST in SSAI nor in SGAI. Proposal: the same SVTA2053 `EXT-X-DATERANGE`
  as the HAND IDs.
- How the manifest is tied to the stitched ad, given that its hash is of the
  mezzanine and not of the segments the player gets.
- Whether c2pa-js can verify a detached manifest in the browser.
