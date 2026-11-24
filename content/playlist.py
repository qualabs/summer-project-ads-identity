"""
playlist.py

Writes and reads the content's HLS playlists. No ffmpeg here: these functions
take the list of segments (name, duration, first PTS) and the breaks, so the
tests can run them without any video.

The ad break is one EXT-X-DATERANGE ID written twice, as RFC 8216 does:

  before the first segment of the break
    #EXT-X-DATERANGE:ID="break-1",START-DATE=...,DURATION=...,SCTE35-OUT=0x...
  before the first segment after it
    #EXT-X-DATERANGE:ID="break-1",START-DATE=...,END-DATE=...,SCTE35-IN=0x...

Both tags sit on a segment boundary and are preceded by an
EXT-X-PROGRAM-DATE-TIME, so the break is located both by position (what
MediaTailor uses) and by date (what a player uses).
"""

import re
from datetime import datetime, timedelta, timezone

import scte35

ATTRIBUTE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def iso(start, ms):
    """start (aware datetime) plus ms milliseconds, in the form HLS wants."""
    t = start + timedelta(milliseconds=ms)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def parse_iso(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def media_playlist(segments, breaks, start_date, cue_tags=False):
    """
    segments: [{"uri", "duration" (s), "pts" (s, first video PTS in the TS)}]
    breaks:   [{"id", "event_id", "first", "last"}]: the break covers
              segments[first..last]; segments[last + 1] is the programme again.
    start_date: aware datetime of the first segment.
    cue_tags: also write EXT-X-CUE-OUT / EXT-X-CUE-IN (see the README).
    """
    # Offsets in whole milliseconds, so START-DATE + DURATION is exactly END-DATE
    offsets, total = [], 0.0
    for s in segments:
        offsets.append(round(total * 1000))
        total += s["duration"]

    opens = {b["first"]: b for b in breaks}
    closes = {b["last"] + 1: b for b in breaks}
    for b in breaks:
        if not 0 < b["first"] <= b["last"] < len(segments) - 1:
            raise ValueError(f"{b['id']}: a break needs programme before and after it")

    target = max(1, round(max(s["duration"] for s in segments) + 0.499))
    out = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]
    for i, s in enumerate(segments):
        if i == 0 or i in opens or i in closes:
            out.append(f"#EXT-X-PROGRAM-DATE-TIME:{iso(start_date, offsets[i])}")
        if i in closes:
            b = closes[i]
            began = offsets[b["first"]]
            out.append(
                f'#EXT-X-DATERANGE:ID="{b["id"]}",START-DATE="{iso(start_date, began)}",'
                f'END-DATE="{iso(start_date, offsets[i])}",'
                f'SCTE35-IN={scte35.placement_end(b["event_id"], s["pts"])}'
            )
            if cue_tags:
                out.append("#EXT-X-CUE-IN")
        if i in opens:
            b = opens[i]
            seconds = (offsets[b["last"] + 1] - offsets[i]) / 1000
            out.append(
                f'#EXT-X-DATERANGE:ID="{b["id"]}",START-DATE="{iso(start_date, offsets[i])}",'
                f"DURATION={seconds:.3f},"
                f'SCTE35-OUT={scte35.placement_start(b["event_id"], s["pts"], seconds)}'
            )
            if cue_tags:
                out.append(f"#EXT-X-CUE-OUT:{seconds:.3f}")
        out += [f"#EXTINF:{s['duration']:.6f},", s["uri"]]
    out.append("#EXT-X-ENDLIST")
    return "\n".join(out) + "\n"


def multivariant_playlist(media_uri, bandwidth, average_bandwidth, width, height, codecs, frame_rate):
    """One variant. MediaTailor needs BANDWIDTH, RESOLUTION and CODECS on it."""
    return (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-INDEPENDENT-SEGMENTS\n"
        f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},AVERAGE-BANDWIDTH={average_bandwidth},"
        f'RESOLUTION={width}x{height},FRAME-RATE={frame_rate:.3f},CODECS="{codecs}"\n'
        f"{media_uri}\n"
    )


def attributes(line):
    """The attribute list of a tag as a dict, without the quotes."""
    return {k: v.strip('"') for k, v in ATTRIBUTE.findall(line.split(":", 1)[1])}


def parse_media(text):
    """
    Read a media playlist back: its segments with their offset and date, and
    the EXT-X-DATERANGE tags with the index of the segment they sit before.
    Enough for the tests and for whoever needs to find the break.
    """
    segments, dateranges, cues = [], [], []
    offset, date, date_at, duration = 0.0, None, 0.0, None
    for line in text.splitlines():
        if line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            date, date_at = parse_iso(line.split(":", 1)[1]), offset
        elif line.startswith("#EXT-X-DATERANGE:"):
            dateranges.append({"before_segment": len(segments), **attributes(line)})
        elif line.startswith("#EXT-X-CUE-"):
            cues.append({"before_segment": len(segments), "tag": line})
        elif line.startswith("#EXTINF:"):
            duration = float(line.split(":", 1)[1].split(",")[0])
        elif line and not line.startswith("#"):
            segments.append({
                "uri": line, "duration": duration, "offset": offset,
                "date": date + timedelta(seconds=offset - date_at) if date else None,
            })
            offset += duration
    return {"segments": segments, "dateranges": dateranges, "cues": cues, "duration": offset}
