"""
make_test_media.py

Generates the synthetic segments the hand-written test playlists point to,
in out/test-media/ (not committed):

  content/seg_000.ts … seg_003.ts   4 x 4 s, test pattern + 440 Hz
  ad/seg_000.ts … seg_002.ts        3 x 4 s, colour bars + 880 Hz

  python player/test/make_test_media.py
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "test-media"


def make(name, video, freq, seconds):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"{video}=size=1280x720:rate=25:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
        "-c:v", "libx264", "-preset", "veryfast", "-g", "100", "-keyint_min", "100",
        "-sc_threshold", "0", "-c:a", "aac", "-b:a", "96k",
        "-f", "hls", "-hls_time", "4", "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(d / "seg_%03d.ts"), str(d / "ffmpeg.m3u8"),
    ], check=True)
    print(f"wrote {d} ({seconds} s)")


if __name__ == "__main__":
    make("content", "testsrc2", 440, 16)
    make("ad", "smptehdbars", 880, 12)
