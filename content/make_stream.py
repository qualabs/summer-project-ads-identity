"""
make_stream.py

Prepares the content stream of the demo: the programme as HLS VOD with an ad
break, marked with SCTE-35 placement opportunity start (0x34) and end (0x35)
in EXT-X-DATERANGE. Both ad paths (SSAI and SGAI) use this same stream.

The break is a stretch of slate (colour bars, silence) cut into the programme,
as long as the ad. Whatever inserts the ad replaces the slate, so no programme
is lost, and bars on screen mean the ad was not inserted.

  python content/make_stream.py media_src/bbb.mp4 --break-at 60

The break duration is the ad's: source.duration in the bridge's hand_ids.json,
or --break-duration. Output goes to out/content/, self-contained and with
relative URLs only.

Needs ffmpeg and ffprobe on the PATH, and threefive (pip install threefive).
"""

import argparse
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import playlist  # noqa: E402

# The playlist's own timeline. EXT-X-DATERANGE needs EXT-X-PROGRAM-DATE-TIME,
# also in VOD; any fixed date works.
START_DATE = "2026-01-01T00:00:00.000Z"
SEGMENT_SECONDS = 6
# What the x264 options below produce: High profile, level 4.0, AAC-LC
CODECS = "avc1.640028,mp4a.40.2"


def probe(src):
    """Frame rate, size, duration and whether there is audio."""
    got = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate",
         "-of", "json", str(src)],
        check=True, capture_output=True, text=True).stdout)
    video = next(s for s in got["streams"] if s["codec_type"] == "video")
    return {
        "fps": Fraction(video["r_frame_rate"]),
        "width": video["width"], "height": video["height"],
        "duration": float(got["format"]["duration"]),
        "audio": any(s["codec_type"] == "audio" for s in got["streams"]),
    }


def plan(break_seconds, break_duration, fps, source_seconds, segment_seconds=SEGMENT_SECONDS):
    """
    Everything in frames, so the cuts are exact. Returns
      pieces: [("programme", first source frame, last + 1 or None) | ("slate", frames)]
      cuts:   output frames where a segment starts (besides 0)
      breaks: [(first output frame of the slate, frames of slate)]
    A break starts on the first frame at or after the time asked for, and the
    slate is never shorter than break_duration (rounded up to a frame).
    """
    total = math.floor(source_seconds * fps)
    slate = math.ceil(Fraction(str(break_duration)) * fps)
    per_segment = round(segment_seconds * fps)
    starts = sorted(math.ceil(Fraction(str(t)) * fps) for t in break_seconds)
    if any(not 0 < s < total for s in starts) or len(set(starts)) != len(starts):
        raise ValueError(f"breaks must be different and inside the programme (0 to {source_seconds:.3f} s)")
    if slate <= 0:
        raise ValueError("the break duration must be positive")

    pieces, cuts, breaks = [], [], []
    position, done = 0, 0  # output frame, source frame

    def grid(length):  # segment starts inside a piece that begins at `position`
        inside = list(range(per_segment, length, per_segment))
        # No sliver at the end of a piece (78.047 s in 6 s segments leaves 0.047 s):
        # the last segment takes it and runs up to 1.5 times the segment length
        if inside and length - inside[-1] < per_segment / 2:
            inside.pop()
        return [position + n for n in inside]

    for s in starts:
        pieces.append(("programme", done, s))
        cuts += grid(s - done)
        position += s - done
        cuts.append(position)
        breaks.append((position, slate))
        pieces.append(("slate", slate))
        cuts += grid(slate)
        position += slate
        cuts.append(position)
        done = s
    pieces.append(("programme", done, None))
    cuts += grid(total - done)
    return pieces, cuts, breaks


def filter_graph(pieces, info, height):
    """Programme pieces and slates, concatenated into one continuous video."""
    fps, rate = info["fps"], f"{info['fps'].numerator}/{info['fps'].denominator}"
    width = round(info["width"] * height / info["height"] / 2) * 2
    programme = [p for p in pieces if p[0] == "programme"]
    seconds = lambda frames: f"{float(Fraction(frames) / fps):.6f}"  # noqa: E731

    g = [f"[0:v]fps={rate},scale={width}:{height},setsar=1,format=yuv420p,"
         f"split={len(programme)}" + "".join(f"[pv{i}]" for i in range(len(programme)))]
    if info["audio"]:
        g.append("[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 f"asplit={len(programme)}" + "".join(f"[pa{i}]" for i in range(len(programme))))
    joined, p = "", 0
    for n, piece in enumerate(pieces):
        if piece[0] == "slate":
            g.append(f"smptebars=size={width}x{height}:rate={rate},format=yuv420p,setsar=1,"
                     f"trim=end_frame={piece[1]}[v{n}]")
            g.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={seconds(piece[1])}[a{n}]")
        else:
            _, first, end = piece
            last = info["duration"] if end is None else float(Fraction(end) / fps)
            frames = f"start_frame={first}" + (f":end_frame={end}" if end is not None else "")
            g.append(f"[pv{p}]trim={frames},setpts=PTS-STARTPTS[v{n}]")
            if info["audio"]:
                times = f"start={seconds(first)}" + (f":end={seconds(end)}" if end is not None else "")
                g.append(f"[pa{p}]atrim={times},asetpts=PTS-STARTPTS[a{n}]")
            else:
                g.append("anullsrc=r=48000:cl=stereo,"
                         f"atrim=duration={last - float(Fraction(first) / fps):.6f}[a{n}]")
            p += 1
        joined += f"[v{n}][a{n}]"
    g.append(f"{joined}concat=n={len(pieces)}:v=1:a=1[v][a]")
    return ";".join(g), width


def encode(src, out_dir, graph, cuts, fps):
    """One encode, with a keyframe and a segment boundary at every cut."""
    # Half a frame early, so rounding never pushes a cut to the next frame
    times = ",".join(f"{float((Fraction(c) - Fraction(1, 2)) / fps):.6f}" for c in cuts)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-force_key_frames", times, "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "128k",
        "-f", "segment", "-segment_times", times, "-segment_format", "mpegts",
        str(out_dir / "seg_%04d.ts"),
    ], check=True)


def measure(path, fps):
    """A segment's first video PTS and its duration, counted in frames."""
    got = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=start_time,nb_read_packets", "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout)["streams"][0]
    frames = int(got["nb_read_packets"])
    return {"uri": path.name, "pts": float(got["start_time"]),
            "duration": float(Fraction(frames) / fps), "frames": frames,
            "bytes": path.stat().st_size}


def locate_breaks(segments, breaks):
    """Find each break in the encoded segments. Fails if a cut did not land on a boundary."""
    starts, frame = {}, 0
    for i, s in enumerate(segments):
        starts[frame] = i
        frame += s["frames"]
    located = []
    for n, (first_frame, slate_frames) in enumerate(breaks, start=1):
        if first_frame not in starts or first_frame + slate_frames not in starts:
            raise SystemExit(f"break {n} is not on a segment boundary: the encode did not cut where planned")
        located.append({"id": f"break-{n}", "event_id": n, "first": starts[first_frame],
                        "last": starts[first_frame + slate_frames] - 1})
    return located


def break_duration_from_bridge(bridge_output):
    path = Path(bridge_output) / "hand_ids.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["source"]["duration"]


def build(src, out, break_at, break_duration, height=720, segment_seconds=SEGMENT_SECONDS,
          cue_tags=False, start_date=START_DATE):
    """Encode, write the playlists and content.json. Returns what content.json holds."""
    src, out = Path(src), Path(out)
    info = probe(src)
    pieces, cuts, breaks = plan(break_at, break_duration, info["fps"], info["duration"], segment_seconds)
    graph, width = filter_graph(pieces, info, height)

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    encode(src, out, graph, cuts, info["fps"])
    segments = [measure(p, info["fps"]) for p in sorted(out.glob("seg_*.ts"))]
    located = locate_breaks(segments, breaks)

    start = playlist.parse_iso(start_date)
    media = playlist.media_playlist(segments, located, start, cue_tags)
    (out / "media.m3u8").write_text(media, encoding="utf-8")
    seconds = sum(s["duration"] for s in segments)
    (out / "index.m3u8").write_text(playlist.multivariant_playlist(
        "media.m3u8",
        bandwidth=math.ceil(max(s["bytes"] * 8 / s["duration"] for s in segments)),
        average_bandwidth=math.ceil(sum(s["bytes"] for s in segments) * 8 / seconds),
        width=width, height=height, codecs=CODECS, frame_rate=float(info["fps"]),
    ), encoding="utf-8")

    parsed = playlist.parse_media(media)
    summary = {
        "source": src.name,
        "playlist": "index.m3u8",
        "media_playlist": "media.m3u8",
        "duration": round(seconds, 3),
        "segments": len(segments),
        "breaks": [{
            "id": d["ID"],
            "start_date": d["START-DATE"],
            "offset": round(parsed["segments"][d["before_segment"]]["offset"], 3),
            "duration": float(d["DURATION"]),
            "first_segment": parsed["segments"][d["before_segment"]]["uri"],
        } for d in parsed["dateranges"] if "SCTE35-OUT" in d],
        "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "content.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("source", help="open-licensed programme video (keep it in media_src/)")
    ap.add_argument("--break-at", type=float, action="append", metavar="SECONDS",
                    help="where the break goes, in programme time; repeat for more breaks (default: 60)")
    ap.add_argument("--break-duration", type=float, metavar="SECONDS",
                    help="override the ad duration read from the bridge output")
    ap.add_argument("--bridge-output", default=str(ROOT / "out" / "bridge"),
                    help="folder with the bridge's hand_ids.json")
    ap.add_argument("--out", default=str(ROOT / "out" / "content"))
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--segment-seconds", type=int, default=SEGMENT_SECONDS)
    ap.add_argument("--cue-tags", action="store_true",
                    help="also write EXT-X-CUE-OUT / EXT-X-CUE-IN at the break (see the README)")
    args = ap.parse_args()

    duration = args.break_duration or break_duration_from_bridge(args.bridge_output)
    if not duration:
        sys.exit(f"No hand_ids.json in {args.bridge_output}: run the bridge on the ad first, "
                 "or pass --break-duration.")
    try:
        summary = build(args.source, args.out, args.break_at or [60.0], duration, args.height,
                        args.segment_seconds, args.cue_tags)
    except ValueError as e:
        sys.exit(str(e))

    print(f"→ {Path(args.out) / 'index.m3u8'}  ({summary['segments']} segments, {summary['duration']} s)")
    for b in summary["breaks"]:
        print(f"  {b['id']}: at {b['offset']} s, {b['duration']} s of slate (ad: {duration} s), "
              f"from {b['first_segment']}")


if __name__ == "__main__":
    main()
