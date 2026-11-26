"""
Tests for the SGAI playlists. No network and no video: a hand-written content
playlist with the break as content/make_stream.py writes it.

  python -m unittest discover sgai
"""

import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_sgai  # noqa: E402

CONTENT = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:9
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
#EXT-X-INDEPENDENT-SEGMENTS
#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:00.000Z
#EXTINF:6.000000,
seg_0000.ts
#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:06.000Z
#EXT-X-DATERANGE:ID="break-1",START-DATE="2026-01-01T00:00:06.000Z",DURATION=13.500,SCTE35-OUT=0xFC30
#EXTINF:6.000000,
seg_0001.ts
#EXTINF:7.500000,
seg_0002.ts
#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:19.500Z
#EXT-X-DATERANGE:ID="break-1",START-DATE="2026-01-01T00:00:06.000Z",END-DATE="2026-01-01T00:00:19.500Z",SCTE35-IN=0xFC30
#EXTINF:6.000000,
seg_0003.ts
#EXT-X-ENDLIST
"""
VAST2SGAI = "https://vast2sgai.example/"
VAST = "https://adserver.example/vast"


def interstitials(text):
    return [make_sgai.attributes(l) for l in text.splitlines()
            if l.startswith("#EXT-X-DATERANGE:") and make_sgai.INTERSTITIAL in l]


class AssetListUrl(unittest.TestCase):
    def test_vasturl_is_encoded_and_carries_the_ad(self):
        url = make_sgai.asset_list_url(VAST2SGAI, VAST, "tampered")
        parts = urlsplit(url)
        self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}",
                         "https://vast2sgai.example/api/asset-list")
        self.assertEqual(parse_qs(parts.query), {"vasturl": [f"{VAST}?ad=tampered"]})
        self.assertNotIn("?ad=", parts.query)  # encoded, not a second query

    def test_vast_with_its_own_query(self):
        url = make_sgai.asset_list_url(VAST2SGAI, f"{VAST}?x=1", "legit")
        self.assertEqual(parse_qs(urlsplit(url).query)["vasturl"], [f"{VAST}?x=1&ad=legit"])


class SgaiPlaylist(unittest.TestCase):
    def setUp(self):
        self.asset_list = make_sgai.asset_list_url(VAST2SGAI, VAST, "legit")
        self.text = make_sgai.sgai_playlist(CONTENT, self.asset_list)

    def test_one_interstitial_with_the_break_timing(self):
        [i] = interstitials(self.text)
        self.assertEqual(i["ID"], "break-1-sgai")
        self.assertEqual(i["START-DATE"], "2026-01-01T00:00:06.000Z")
        self.assertEqual(i["DURATION"], "13.500")
        self.assertEqual(i["X-ASSET-LIST"], self.asset_list)
        # Resume after the whole break (the bars), not after the ad
        self.assertEqual(i["X-RESUME-OFFSET"], "13.500")

    def test_right_after_the_break_tag(self):
        lines = self.text.splitlines()
        at = next(n for n, l in enumerate(lines) if "SCTE35-OUT=" in l)
        self.assertIn(make_sgai.INTERSTITIAL, lines[at + 1])
        self.assertTrue(lines[at + 2].startswith("#EXTINF:"))

    def test_the_rest_is_the_content_unchanged(self):
        without = [l for l in self.text.splitlines() if make_sgai.INTERSTITIAL not in l]
        self.assertEqual(without, CONTENT.splitlines())

    def test_no_hand_ids(self):
        self.assertNotIn("X-AD-CREATIVE-SIGNALING", self.text)
        self.assertNotIn("10.23/", self.text)

    def test_segments_base(self):
        text = make_sgai.sgai_playlist(CONTENT, self.asset_list, "../content/")
        segs = [l for l in text.splitlines() if l and not l.startswith("#")]
        self.assertEqual(segs[0], "../content/seg_0000.ts")
        text = make_sgai.sgai_playlist(CONTENT, self.asset_list, "https://cdn.example/content/")
        segs = [l for l in text.splitlines() if l and not l.startswith("#")]
        self.assertEqual(segs[-1], "https://cdn.example/content/seg_0003.ts")

    def test_one_interstitial_per_break(self):
        two = CONTENT.replace("seg_0003.ts\n", (
            "seg_0003.ts\n"
            '#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:25.500Z\n'
            '#EXT-X-DATERANGE:ID="break-2",START-DATE="2026-01-01T00:00:25.500Z",DURATION=6.000,SCTE35-OUT=0xFC30\n'
            "#EXTINF:6.000000,\nseg_0004.ts\n"))
        ids = [i["ID"] for i in interstitials(make_sgai.sgai_playlist(two, self.asset_list))]
        self.assertEqual(ids, ["break-1-sgai", "break-2-sgai"])


class BadInput(unittest.TestCase):
    def test_no_break(self):
        no_break = "\n".join(l for l in CONTENT.splitlines() if "DATERANGE" not in l)
        with self.assertRaises(ValueError):
            make_sgai.sgai_playlist(no_break, "x")

    def test_break_without_duration(self):
        with self.assertRaises(ValueError):
            make_sgai.sgai_playlist(CONTENT.replace("DURATION=13.500,", ""), "x")

    def test_already_has_an_interstitial(self):
        once = make_sgai.sgai_playlist(CONTENT, "x")
        with self.assertRaises(ValueError):
            make_sgai.sgai_playlist(once, "x")

    def test_multivariant_playlist(self):
        with self.assertRaises(ValueError):
            make_sgai.sgai_playlist("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nmedia.m3u8\n", "x")


if __name__ == "__main__":
    unittest.main()
