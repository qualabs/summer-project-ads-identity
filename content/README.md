# Content stream

## The question it answers

Can one HLS VOD stream, with the ad break marked by SCTE-35 placement
opportunity start (`0x34`) and end (`0x35`), be the content for both ad paths:
SSAI with MediaTailor and SGAI with vast-2-sgai?

## What it does

`make_stream.py` takes the programme (an open-licensed video) and writes the
content stream of the demo:

- the programme re-encoded to 720p H.264/AAC and cut into 6 s MPEG-TS segments
- one ad break, as long as the ad, where **colour bars and silence** are cut
  into the programme. Whatever inserts the ad replaces the bars, so no
  programme is lost, and bars on screen mean the ad was not inserted
- a segment boundary (and a keyframe) exactly at the start and at the end of
  the break
- the break marked in the media playlist with `EXT-X-DATERANGE`, carrying a
  SCTE-35 `time_signal` built with [threefive](https://github.com/superkabuki/threefive)

```
#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:01:00.000Z
#EXT-X-DATERANGE:ID="break-1",START-DATE="2026-01-01T00:01:00.000Z",DURATION=78.083,SCTE35-OUT=0xFC302C…
#EXTINF:6.000000,
seg_0010.ts
…
#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:02:18.083Z
#EXT-X-DATERANGE:ID="break-1",START-DATE="2026-01-01T00:01:00.000Z",END-DATE="2026-01-01T00:02:18.083Z",SCTE35-IN=0xFC3027…
#EXTINF:6.000000,
seg_0023.ts
```

`SCTE35-OUT` is the `0x34` with the break duration; `SCTE35-IN` is the `0x35`.
They share the `ID` and the `segmentation_event_id`. Their `pts_time` is the
first video PTS of the segment they sit before. The cues only mark the break:
no UPID and no HAND IDs (contract 3 in [CONTRACTS.md](../CONTRACTS.md)).

The break duration is the ad's: `source.duration` in the bridge's
`hand_ids.json`, rounded **up** to a whole frame so the ad always fits
(78.047 s becomes 78.083 s at 24 fps).

## Run it

Needs `ffmpeg` and `ffprobe` on the PATH, Python 3.9+ and threefive
(`pip install threefive`; tested with 3.1.11).

Put an open-licensed programme in `media_src/` (git-ignored). For example
Tears of Steel, (CC) Blender Foundation, CC BY 3.0:
`https://download.blender.org/demo/movies/ToS/tears_of_steel_720p.mov` (372 MB).

```bash
python pipeline/bridge.py media_src/signed_ad.mp4
python content/make_stream.py media_src/tears_of_steel_720p.mov
```

| Option | Default | What it is |
|--------|---------|------------|
| `--break-at` | `60` | where the break goes, in seconds of programme; repeat it for more breaks |
| `--break-duration` | from the bridge | override the ad duration |
| `--bridge-output` | `out/bridge` | folder with the bridge's `hand_ids.json` |
| `--out` | `out/content` | output folder; it is emptied first |
| `--height` | `720` | height of the rendition |
| `--segment-seconds` | `6` | segment length |
| `--cue-tags` | off | also write `EXT-X-CUE-OUT` / `EXT-X-CUE-IN` at the break (see below) |

Without a `hand_ids.json` and without `--break-duration` it stops and writes
nothing.

The output is self-contained and has only relative URLs, so the folder can be
copied as it is to S3:

```
out/content/
  index.m3u8      multivariant playlist, one variant
  media.m3u8      media playlist with the break
  seg_0000.ts …
  content.json    where the break is (offset, date, duration, first segment)
```

Decode a cue from the playlist:

```bash
python content/scte35.py 0xFC302C…
```

## Tests

```bash
python -m unittest discover content
```

They don't need the programme. The playlist tests use a made-up list of
segments; the end-to-end one encodes 12 s of ffmpeg's `testsrc` and is skipped
without ffmpeg. They parse the playlist, decode the SCTE-35 with threefive and
check the segmentation types `0x34` / `0x35`, that the break starts and ends on
a segment boundary, and that the duration is the same in the tag, in the cue,
between the dates and in the segments.

## Check it in hls.js

```bash
python -m http.server 8000
```

Open `http://localhost:8000/content/check.html` (`?src=` picks another
playlist). The page plays the stream with hls.js 1.5.17 and lists the
`EXT-X-DATERANGE` hls.js parsed and the metadata cues it put on the video.

## What each consumer expects as the break marker

Checked in the docs and the source, not yet against the running tools.

**MediaTailor (SSAI).** Its
[HLS ad markers](https://docs.aws.amazon.com/mediatailor/latest/ug/hls-ad-markers.html)
are `EXT-X-CUE-OUT`/`EXT-X-CUE-IN`, `EXT-X-DATERANGE` and
`EXT-X-SPLICEPOINT-SCTE35`.

- `EXT-X-DATERANGE` is accepted as `SCTE35-OUT` + `DURATION`, as a
  `SCTE35-OUT` / `SCTE35-IN` pair, or both. We write both.
- It ignores `START-DATE`: the break is where the tag is in the playlist. So
  the tags sit exactly on the segment boundaries.
- `SCTE35-CMD` is not listed as a marker.
- The docs do not say that the `SCTE35-OUT` value is decoded (their example is
  `0xF`). The only place they ask for `0x34` / `0x35` is
  `EXT-X-SPLICEPOINT-SCTE35`.
- For VOD, every example in the docs uses `#EXT-X-CUE-OUT: 0` + `#EXT-X-CUE-IN`
  (insert, replace nothing); a marker with a duration replaces that much
  content. `EXT-X-DATERANGE` on VOD is not shown in any example. That is why
  the break here is slate to be replaced, and why `--cue-tags` exists: if
  MediaTailor does not act on the `EXT-X-DATERANGE` in VOD, the same break can
  carry `EXT-X-CUE-OUT:<duration>` / `EXT-X-CUE-IN` too.
- It needs a multivariant playlist whose `EXT-X-STREAM-INF` has `BANDWIDTH`,
  `RESOLUTION` and `CODECS`. `index.m3u8` has them.
- It [passes `EXT-X-DATERANGE` through](https://docs.aws.amazon.com/mediatailor/latest/ug/manifest-hls-tags.html)
  to its output, so the player will see the break's `SCTE35-OUT` after stitching.

**vast-2-sgai (SGAI).** [vast-2-sgai](https://github.com/montevideo-tech/vast-2-sgai)
does not read the content playlist at all. It turns a VAST into an HLS
Interstitials asset list (`GET /api/asset-list`) and nothing else: it detects
no SCTE-35, no `EXT-X-CUE-OUT`, no `EXT-X-DATERANGE`. In its samples the
interstitial tag is written by hand in the content playlist:

```
#EXT-X-DATERANGE:ID="ad1",CLASS="com.apple.hls.interstitial",START-DATE="…",DURATION=45.000,X-ASSET-LIST="/api/asset-list?vasturl=…",X-RESUME-OFFSET=0
```

So the two paths need different things, and one marker form does not serve
both: MediaTailor reads the SCTE-35 `EXT-X-DATERANGE` written here, while SGAI
needs a second `EXT-X-DATERANGE` of class `com.apple.hls.interstitial` at the
same place, pointing at vast-2-sgai. **This folder does not write that tag**:
it is a step of the SGAI path. `content.json` and the `break-1` tag give it
what it needs: `START-DATE` is the break's start, and `X-RESUME-OFFSET` must be
the break's `DURATION` so the player skips the slate.

## What we found

- One command writes the stream. With the current ad (78.047 s) and the
  default break at 60 s, the break is 78.083 s: 13 segments of bars from
  `seg_0010.ts`.
- 78.047 s in 6 s segments would leave a last segment of 0.047 s, which
  ffprobe could not even open. The last segment of each piece takes the
  remainder instead, so a segment can be up to 9 s (`EXT-X-TARGETDURATION` says
  so).
- hls.js 1.5.17 plays the stream across both edges of the break and merges the
  two tags of `break-1` into one date range, 60.000 s to 138.083 s, with both
  `SCTE35-OUT` and `SCTE35-IN`. It also exposes them as metadata cues on the
  video element.

What was verified, and with what:

| | With |
|---|---|
| Segmentation types, boundaries, duration | the tests (synthetic clips) |
| Default run, duration from the bridge's `hand_ids.json` | a 150 s synthetic 720p clip |
| Playback and date range in hls.js | the same synthetic clips, in Chromium |

Not verified:

- **The real programme.** No open-licensed video was in `media_src/` when this
  was built; only synthetic clips went through the script.
- **MediaTailor and vast-2-sgai themselves.** Nothing here ran against either
  (there is no AWS account yet). Whether MediaTailor acts on
  `EXT-X-DATERANGE` in a VOD source is the first thing to test.
- Safari / native HLS.

## Limitations and next steps

- One rendition only. An ABR ladder would need the break in every media
  playlist.
- A break cannot be a pre-roll or a post-roll: it needs programme before and
  after it.
- The bars have no text on them (ffmpeg's `drawtext` is not in every build).
- The SGAI interstitial tag, described above.
