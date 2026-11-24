"""
Tests for the content stream. They never need the real programme: the playlist
tests use a made-up list of segments, and the end-to-end one encodes a few
seconds of ffmpeg's testsrc (skipped when ffmpeg is not installed).

  python -m unittest discover content
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_stream  # noqa: E402
import playlist  # noqa: E402
import scte35  # noqa: E402

START = playlist.parse_iso("2026-01-01T00:00:00.000Z")
# 2 programme segments, 3 of break (13.5 s), 2 of programme. PTS as in a TS: not from zero.
DURATIONS = [6.0, 4.0, 6.0, 6.0, 1.5, 6.0, 2.0]
BREAK = {"id": "break-1", "event_id": 1, "first": 2, "last": 4}


def segments():
    out, pts = [], 1.4
    for i, d in enumerate(DURATIONS):
        out.append({"uri": f"seg_{i:04d}.ts", "duration": d, "pts": pts})
        pts += d
    return out


def assert_break(test, text, at, seconds, tolerance=0.0):
    """The checks shared by the synthetic and the encoded playlist. Returns the parsed playlist."""
    parsed = playlist.parse_media(text)
    segs = parsed["segments"]
    out = [d for d in parsed["dateranges"] if "SCTE35-OUT" in d]
    back = [d for d in parsed["dateranges"] if "SCTE35-IN" in d]
    test.assertEqual((len(out), len(back)), (1, 1))
    out, back = out[0], back[0]
    test.assertEqual(out["ID"], back["ID"])
    test.assertEqual(out["START-DATE"], back["START-DATE"])

    # Segmentation types, decoded with threefive
    start, end = scte35.decode(out["SCTE35-OUT"]), scte35.decode(back["SCTE35-IN"])
    test.assertEqual(start["command"], "Time Signal")
    test.assertEqual(start["segmentation_type_id"], 0x34)
    test.assertEqual(end["segmentation_type_id"], 0x35)
    test.assertEqual(start["segmentation_event_id"], end["segmentation_event_id"])
    test.assertEqual((start["upid_length"], end["upid_length"]), (0, 0))  # marks the break, no IDs

    # Position: on a segment boundary, and the dates agree with the segments
    first, after = segs[out["before_segment"]], segs[back["before_segment"]]
    test.assertAlmostEqual(first["offset"], at, delta=tolerance + 0.0005)
    test.assertEqual(playlist.parse_iso(out["START-DATE"]), first["date"])
    test.assertEqual(playlist.parse_iso(back["END-DATE"]), after["date"])
    test.assertLess(abs(first["date"] - (START + timedelta(seconds=first["offset"]))),
                    timedelta(milliseconds=1))

    # Duration: the same in the tag, in the cue, between the dates and in the segments
    duration = float(out["DURATION"])
    test.assertAlmostEqual(duration, seconds, delta=tolerance + 0.0005)
    test.assertGreaterEqual(duration + 0.0005, seconds)  # never shorter than the ad
    test.assertAlmostEqual(start["segmentation_duration"], duration, places=3)
    test.assertAlmostEqual((after["date"] - first["date"]).total_seconds(), duration, places=3)
    test.assertAlmostEqual(after["offset"] - first["offset"], duration, places=3)
    test.assertAlmostEqual(end["pts_time"] - start["pts_time"], duration, places=3)
    return parsed


class Scte35(unittest.TestCase):
    def test_start_is_0x34_with_the_duration(self):
        cue = scte35.decode(scte35.placement_start(7, 61.4, 78.047))
        self.assertEqual(cue["segmentation_type_id"], 0x34)
        self.assertEqual(cue["segmentation_message"], "Provider Placement Opportunity Start")
        self.assertEqual(cue["segmentation_event_id"], 7)
        self.assertAlmostEqual(cue["segmentation_duration"], 78.047, places=3)
        self.assertAlmostEqual(cue["pts_time"], 61.4, places=3)

    def test_end_is_0x35_without_duration(self):
        cue = scte35.decode(scte35.placement_end(7, 139.447))
        self.assertEqual(cue["segmentation_type_id"], 0x35)
        self.assertEqual(cue["segmentation_message"], "Provider Placement Opportunity End")
        self.assertIsNone(cue["segmentation_duration"])

    def test_hls_form_is_hex(self):
        self.assertTrue(scte35.placement_end(1, 61.4).startswith("0xFC30"))


class MediaPlaylist(unittest.TestCase):
    def test_break_is_marked_on_the_segment_boundary(self):
        text = playlist.media_playlist(segments(), [BREAK], START)
        parsed = assert_break(self, text, at=10.0, seconds=13.5)
        self.assertEqual([d["before_segment"] for d in parsed["dateranges"]], [2, 5])
        self.assertEqual(parsed["cues"], [])

    def test_cue_pts_is_the_segment_pts(self):
        parsed = playlist.parse_media(playlist.media_playlist(segments(), [BREAK], START))
        out, back = parsed["dateranges"]
        self.assertAlmostEqual(scte35.decode(out["SCTE35-OUT"])["pts_time"], 11.4, places=3)
        self.assertAlmostEqual(scte35.decode(back["SCTE35-IN"])["pts_time"], 24.9, places=3)

    def test_vod_playlist_with_program_date_time(self):
        text = playlist.media_playlist(segments(), [BREAK], START)
        lines = text.splitlines()
        self.assertIn("#EXT-X-PLAYLIST-TYPE:VOD", lines)
        self.assertEqual(lines[-1], "#EXT-X-ENDLIST")
        self.assertIn("#EXT-X-TARGETDURATION:6", lines)
        # A date before the first segment and before each DATERANGE
        self.assertLess(lines.index("#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:00.000Z"),
                        lines.index("seg_0000.ts"))
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-DATERANGE"):
                self.assertTrue(lines[i - 1].startswith("#EXT-X-PROGRAM-DATE-TIME:"))

    def test_urls_are_relative(self):
        text = playlist.media_playlist(segments(), [BREAK], START)
        uris = [s["uri"] for s in playlist.parse_media(text)["segments"]]
        self.assertEqual(len(uris), len(DURATIONS))
        self.assertTrue(all("/" not in u and ":" not in u for u in uris))

    def test_cue_tags_only_when_asked(self):
        parsed = playlist.parse_media(playlist.media_playlist(segments(), [BREAK], START, cue_tags=True))
        self.assertEqual(parsed["cues"], [{"before_segment": 2, "tag": "#EXT-X-CUE-OUT:13.500"},
                                          {"before_segment": 5, "tag": "#EXT-X-CUE-IN"}])

    def test_two_breaks_have_their_own_id_and_event(self):
        segs = segments() + segments()
        for i, s in enumerate(segs):
            s["uri"] = f"seg_{i:04d}.ts"
        second = {"id": "break-2", "event_id": 2, "first": 9, "last": 11}
        parsed = playlist.parse_media(playlist.media_playlist(segs, [BREAK, second], START))
        outs = [d for d in parsed["dateranges"] if "SCTE35-OUT" in d]
        self.assertEqual([d["ID"] for d in outs], ["break-1", "break-2"])
        self.assertEqual([scte35.decode(d["SCTE35-OUT"])["segmentation_event_id"] for d in outs], [1, 2])

    def test_break_needs_programme_around_it(self):
        for bad in ({**BREAK, "first": 0}, {**BREAK, "last": len(DURATIONS) - 1}):
            with self.assertRaises(ValueError):
                playlist.media_playlist(segments(), [bad], START)

    def test_multivariant_has_what_mediatailor_asks_for(self):
        text = playlist.multivariant_playlist("media.m3u8", 2000000, 1500000, 1280, 720,
                                              make_stream.CODECS, 24.0)
        info = playlist.attributes(next(l for l in text.splitlines() if l.startswith("#EXT-X-STREAM-INF")))
        self.assertEqual((info["BANDWIDTH"], info["RESOLUTION"]), ("2000000", "1280x720"))
        self.assertIn("CODECS", info)
        self.assertEqual(text.splitlines()[-1], "media.m3u8")


class Plan(unittest.TestCase):
    def test_cuts_at_the_break_and_at_its_end(self):
        pieces, cuts, breaks = make_stream.plan([10], 13.5, Fraction(25), 30, segment_seconds=6)
        self.assertEqual(pieces, [("programme", 0, 250), ("slate", 338), ("programme", 250, None)])
        self.assertEqual(breaks, [(250, 338)])
        self.assertEqual(cuts, [150, 250, 400, 588, 738, 888])

    def test_no_sliver_segment_at_the_end_of_the_break(self):
        # 78.047 s in 6 s segments: 12 full ones and 0.047 s that must not be a segment
        _, cuts, breaks = make_stream.plan([60], 78.047, Fraction(24), 600)
        first, frames = breaks[0]
        inside = [c for c in cuts if first < c < first + frames]
        self.assertEqual(len(inside), 12)
        self.assertEqual(first + frames - inside[-1], 6 * 24 + 2)

    def test_slate_is_never_shorter_than_the_ad(self):
        fps = Fraction(24000, 1001)
        _, _, breaks = make_stream.plan([60], 78.047, fps, 600)
        self.assertGreaterEqual(Fraction(breaks[0][1]) / fps, Fraction("78.047"))
        self.assertLess(Fraction(breaks[0][1] - 1) / fps, Fraction("78.047"))

    def test_break_outside_the_programme_is_refused(self):
        for at in (0, 30, 45):
            with self.assertRaises(ValueError):
                make_stream.plan([at], 5, Fraction(25), 30)

    def test_duration_comes_from_the_bridge_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(make_stream.break_duration_from_bridge(tmp))
            (Path(tmp) / "hand_ids.json").write_text(json.dumps({"source": {"duration": 78.047}}))
            self.assertEqual(make_stream.break_duration_from_bridge(tmp), 78.047)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
class OutputFolder(unittest.TestCase):
    def test_only_its_own_files_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ours = ["index.m3u8", "media.m3u8", "content.json", "seg_0000.ts", "seg_0042.ts"]
            theirs = ["programme.mp4", "notes.txt", "other.m3u8"]
            for name in ours + theirs:
                (out / name).write_text("x")
            (out / "keep").mkdir()
            make_stream.clear_output(out)
            self.assertEqual({p.name for p in out.iterdir()}, set(theirs) | {"keep"})

    def test_missing_folder_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "a" / "b"
            make_stream.clear_output(out)
            self.assertTrue(out.is_dir())


class EndToEnd(unittest.TestCase):
    """Encodes 12 s of testsrc at 29.97 fps (the awkward frame rate) with a 3.3 s break."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "content"
        clip = Path(cls.tmp.name) / "clip.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30000/1001:duration=12",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(clip),
        ], check=True)
        cls.summary = make_stream.build(clip, cls.out, [5.0], 3.3, height=180, segment_seconds=2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_break_in_the_encoded_stream(self):
        frame = 1001 / 30000
        parsed = assert_break(self, (self.out / "media.m3u8").read_text(), at=5.0, seconds=3.3,
                              tolerance=frame)
        self.assertAlmostEqual(parsed["duration"], 12 + 3.3, delta=3 * frame)

    def test_cue_pts_is_where_the_segment_starts(self):
        parsed = playlist.parse_media((self.out / "media.m3u8").read_text())
        for d in parsed["dateranges"]:
            cue = scte35.decode(d.get("SCTE35-OUT") or d["SCTE35-IN"])
            seg = self.out / parsed["segments"][d["before_segment"]]["uri"]
            self.assertAlmostEqual(cue["pts_time"], make_stream.measure(seg, Fraction(30000, 1001))["pts"],
                                   places=3)

    def test_folder_is_self_contained(self):
        parsed = playlist.parse_media((self.out / "media.m3u8").read_text())
        names = {p.name for p in self.out.iterdir()}
        self.assertEqual(names, {"index.m3u8", "media.m3u8", "content.json"}
                         | {s["uri"] for s in parsed["segments"]})
        self.assertIn("\nmedia.m3u8\n", (self.out / "index.m3u8").read_text())

    def test_every_segment_starts_with_a_keyframe(self):
        for seg in sorted(self.out.glob("seg_*.ts")):
            flags = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+#1",
                 "-show_entries", "packet=flags", "-of", "csv=p=0", str(seg)],
                check=True, capture_output=True, text=True).stdout
            self.assertTrue(flags.startswith("K"), seg.name)

    def test_summary_points_at_the_break(self):
        on_disk = json.loads((self.out / "content.json").read_text())
        self.assertEqual(on_disk, self.summary)
        self.assertEqual(len(on_disk["breaks"]), 1)
        self.assertAlmostEqual(on_disk["breaks"][0]["offset"], 5.0, delta=0.04)


if __name__ == "__main__":
    unittest.main()
