"""
Tests for package_ad.py that need no mezzanine, c2patool or ffmpeg.

  python -m unittest discover ad-packaging
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_ad  # noqa: E402

FFMPEG_PLAYLIST = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:4
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:4.000000,
seg_000.ts
#EXTINF:4.000000,
seg_001.ts
#EXT-X-ENDLIST
"""
DATERANGE = '#EXT-X-DATERANGE:ID="ad-1",CLASS="x",START-DATE="2026-01-01T00:00:00.000Z"'
HAND_ID = re.compile(r"^10\.\d+/[0-9A-F]{4}(-[0-9A-F]{4}){4}$")


class WithDaterange(unittest.TestCase):
    def test_once_before_the_first_segment(self):
        lines = package_ad.with_daterange(FFMPEG_PLAYLIST, DATERANGE).splitlines()
        first = lines.index("#EXTINF:4.000000,")
        self.assertEqual(lines[first - 2], f"#EXT-X-PROGRAM-DATE-TIME:{package_ad.PDT}")
        self.assertEqual(lines[first - 1], DATERANGE)
        self.assertEqual(sum(l.startswith("#EXT-X-DATERANGE") for l in lines), 1)
        self.assertEqual(sum(l.startswith("#EXT-X-PROGRAM-DATE-TIME") for l in lines), 1)

    def test_replaces_an_existing_program_date_time(self):
        src = FFMPEG_PLAYLIST.replace("#EXTINF", "#EXT-X-PROGRAM-DATE-TIME:2020-01-01T00:00:00Z\n#EXTINF", 1)
        out = package_ad.with_daterange(src, DATERANGE)
        self.assertNotIn("2020-01-01", out)
        self.assertEqual(out.count("#EXT-X-PROGRAM-DATE-TIME"), 1)

    def test_segment_prefix_only_on_uris(self):
        lines = package_ad.with_daterange(FFMPEG_PLAYLIST, DATERANGE, "../legit/").splitlines()
        uris = [l for l in lines if l and not l.startswith("#")]
        self.assertEqual(uris, ["../legit/seg_000.ts", "../legit/seg_001.ts"])
        self.assertIn("#EXT-X-ENDLIST", lines)

    def test_keeps_everything_else(self):
        out = package_ad.with_daterange(FFMPEG_PLAYLIST, DATERANGE)
        for line in FFMPEG_PLAYLIST.splitlines():
            self.assertIn(line, out)


class TamperedId(unittest.TestCase):
    def test_different_and_well_formed(self):
        for value in ("10.23/AAAA-AAAA-AAAA-AAAA-A2D7", "10.23/AAAA-AAAA-AAAA-AAAA-0004"):
            changed = package_ad.tampered_id(value)
            self.assertNotEqual(changed, value)
            self.assertRegex(changed, HAND_ID)
            self.assertEqual(changed.rsplit("-", 1)[0], value.rsplit("-", 1)[0])

    def test_all_zero_group(self):
        self.assertEqual(package_ad.tampered_id("10.23/AAAA-AAAA-AAAA-AAAA-0000"),
                         "10.23/AAAA-AAAA-AAAA-AAAA-FFFF")


class ClearOutputs(unittest.TestCase):
    def test_removes_only_what_the_script_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out, bridge_dir = tmp / "out", tmp / "bridge"
            for v in ("legit", "tampered", "default"):
                (out / v).mkdir(parents=True)
                (out / v / "index.m3u8").write_text("x")
            (out / "ad.json").write_text("{}")
            (out / "mezzanine.mp4").write_text("keep me")   # e.g. --out media_src
            (out / "other").mkdir()
            for d in (bridge_dir, bridge_dir / "legit", bridge_dir / "tampered"):
                d.mkdir(parents=True, exist_ok=True)
                (d / "hand_ids.json").write_text("{}")
            (bridge_dir / "svta2053.json").write_text("{}")

            package_ad.clear_outputs(bridge_dir, out)

            self.assertEqual(sorted(p.name for p in out.iterdir()), ["mezzanine.mp4", "other"])
            self.assertEqual(list(bridge_dir.rglob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
