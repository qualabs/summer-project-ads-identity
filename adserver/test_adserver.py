"""
Tests for the ad server. HAND IDs here are placeholders, never real ones.

  python -m unittest discover adserver
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lambda_handler  # noqa: E402
import server  # noqa: E402
import source  # noqa: E402
import vast  # noqa: E402

T01 = "10.23/AAAA-AAAA-AAAA-AAAA-0001"
T02 = "10.23/AAAA-AAAA-AAAA-AAAA-0002"
T04 = "10.23/AAAA-AAAA-AAAA-AAAA-0004"
MEDIA = {"mp4": "https://cdn.test/ad.mp4", "hls": "https://cdn.test/index.m3u8", "width": 1280, "height": 720}


def hand_ids(hand=None, seconds=78.047):
    return {
        "ad_id": "QLAB0000001H",
        "hand": hand or {"type01": T01, "type02": T02, "type04": T04},
        "resolver": "https://doi.org/",
        "source": {"file": "signed_ad.mp4", "duration": seconds},
    }


class Vast(unittest.TestCase):
    def test_follows_the_contract(self):
        root = ET.fromstring(vast.build(hand_ids(), MEDIA))
        self.assertEqual(root.tag, "VAST")
        self.assertEqual(root.get("version"), "4.2")
        self.assertEqual(root.find("Ad").get("id"), "QLAB0000001H")
        self.assertEqual(root.findtext("Ad/InLine/AdSystem"), "ads-identity-demo")
        # Empty, and before Creatives, the order VAST gives the InLine.
        inline = [child.tag for child in root.find("Ad/InLine")]
        self.assertEqual(root.findtext("Ad/InLine/Impression"), "")
        self.assertLess(inline.index("Impression"), inline.index("Creatives"))

        universal = root.find("Ad/InLine/Creatives/Creative/UniversalAdId")
        self.assertEqual((universal.get("idRegistry"), universal.text), ("ad-id.org", "QLAB0000001H"))
        self.assertEqual(root.findtext("Ad/InLine/Creatives/Creative/Linear/Duration"), "00:01:18.047")

        files = root.findall("Ad/InLine/Creatives/Creative/Linear/MediaFiles/MediaFile")
        self.assertEqual([(f.get("delivery"), f.get("type"), f.text) for f in files], [
            ("progressive", "video/mp4", MEDIA["mp4"]),
            ("streaming", "application/x-mpegURL", MEDIA["hls"]),
        ])
        self.assertTrue(all(f.get("width") == "1280" and f.get("height") == "720" for f in files))

        extension = root.find("Ad/InLine/Extensions/Extension")
        self.assertEqual(extension.get("type"), "hand-id")
        self.assertEqual([(h.get("type"), h.text) for h in extension.findall("HandId")], [
            ("01", "https://doi.org/" + T01),
            ("02", "https://doi.org/" + T02),
            ("04", "https://doi.org/" + T04),
        ])

    def test_type04_is_optional(self):
        root = ET.fromstring(vast.build(hand_ids({"type01": T01, "type02": T02}), MEDIA))
        self.assertEqual([h.get("type") for h in root.iter("HandId")], ["01", "02"])

    def test_refuses_an_ad_without_type01_or_type02(self):
        for hand in ({"type02": T02}, {"type01": T01}):
            with self.assertRaises(ValueError):
                vast.build(hand_ids(hand), MEDIA)

    def test_duration(self):
        self.assertEqual(vast.duration(30), "00:00:30.000")
        self.assertEqual(vast.duration(78.6), "00:01:18.600")  # never rounded up to 00:01:19
        self.assertEqual(vast.duration(59.9996), "00:01:00.000")
        self.assertEqual(vast.duration(3725.2), "01:02:05.200")

    def test_empty_has_no_ad(self):
        root = ET.fromstring(vast.empty())
        self.assertEqual((root.tag, root.get("version"), len(root)), ("VAST", "4.2", 0))


class Server(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bridge = Path(tmp.name)
        handler = server.make_handler(self.bridge, "https://cdn.test/ads/")
        handler.log_message = lambda *a: None
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def write(self, folder, content):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "hand_ids.json").write_text(content, encoding="utf-8")

    def get(self, path):
        url = f"http://127.0.0.1:{self.httpd.server_address[1]}{path}"
        try:
            with urllib.request.urlopen(url) as r:
                return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def test_serves_the_default_bridge_output(self):
        self.write(self.bridge, json.dumps(hand_ids()))
        status, headers, body = self.get("/vast")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/xml; charset=utf-8")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        root = ET.fromstring(body)
        self.assertEqual(len(list(root.iter("HandId"))), 3)
        self.assertTrue(all((f.get("width"), f.get("height")) == ("1280", "720") for f in root.iter("MediaFile")))
        self.assertEqual([f.text for f in root.iter("MediaFile")],
                         ["https://cdn.test/ads/default/ad.mp4", "https://cdn.test/ads/default/index.m3u8"])

    def test_serves_a_named_ad(self):
        self.write(self.bridge / "legit", json.dumps(hand_ids()))
        root = ET.fromstring(self.get("/vast?ad=legit")[2])
        self.assertEqual([f.text for f in root.iter("MediaFile")],
                         ["https://cdn.test/ads/legit/ad.mp4", "https://cdn.test/ads/legit/index.m3u8"])

    def test_no_bridge_output_means_no_ad(self):
        self.write(self.bridge / "legit", json.dumps(hand_ids()))
        for path in ("/vast", "/vast?ad=tampered"):
            status, _, body = self.get(path)
            self.assertEqual(status, 200)
            self.assertEqual(len(ET.fromstring(body)), 0, path)

    def test_unusable_bridge_output_means_no_ad(self):
        broken = hand_ids()
        del broken["hand"]["type02"]
        self.write(self.bridge, json.dumps(broken))
        self.assertEqual(len(ET.fromstring(self.get("/vast")[2])), 0)
        self.write(self.bridge, "{not json")
        self.assertEqual(len(ET.fromstring(self.get("/vast")[2])), 0)

    def test_rejects_names_that_leave_the_bridge_dir(self):
        self.assertEqual(self.get("/vast?ad=../secret")[0], 400)
        self.assertEqual(self.get("/vast?ad=")[0], 200)  # blank value is dropped: default ad
        self.assertEqual(self.get("/other")[0], 404)


class FakeS3:
    """The two things source._s3 uses from a boto3 client."""

    class exceptions:
        class NoSuchKey(Exception):
            pass

    class ClientError(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    def __init__(self, objects, missing=None):
        self.objects = objects
        self.missing = missing  # error code for a missing key; NoSuchKey when None

    def get_object(self, Bucket, Key):
        try:
            data = self.objects[(Bucket, Key)]
        except KeyError:
            if self.missing:
                raise self.ClientError(self.missing)
            raise self.exceptions.NoSuchKey(Key)
        return {"Body": type("Body", (), {"read": lambda self: data})()}


class Source(unittest.TestCase):
    def serve(self, folder):
        class Quiet(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(folder), **kwargs)

            def log_message(self, *args):
                pass

        handler = Quiet
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    def folder(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        (folder / "legit").mkdir()
        (folder / "hand_ids.json").write_text(json.dumps(hand_ids()), encoding="utf-8")
        (folder / "legit" / "hand_ids.json").write_text(json.dumps(hand_ids()), encoding="utf-8")
        return folder

    def check(self, read):
        self.assertEqual(read(None), hand_ids())
        self.assertEqual(read("legit"), hand_ids())
        self.assertIsNone(read("tampered"))

    def test_local_folder(self):
        self.check(source.reader(self.folder()))

    def test_http_base_url(self):
        self.check(source.reader(self.serve(self.folder()) + "/"))

    def test_http_failure_is_not_a_missing_ad(self):
        with self.assertRaises(OSError):
            source.reader("http://127.0.0.1:1/bridge")(None)

    def test_s3_prefix(self):
        data = json.dumps(hand_ids()).encode()
        fake = FakeS3({("bucket", "bridge/hand_ids.json"): data,
                       ("bucket", "bridge/legit/hand_ids.json"): data})
        self.check(source.reader("s3://bucket/bridge/", s3_client=fake))
        root = FakeS3({("bucket", "hand_ids.json"): data})
        self.assertEqual(source.reader("s3://bucket", s3_client=root)(None), hand_ids())
        with self.assertRaises(ValueError):
            source.reader("s3://")

    def test_s3_access_denied_is_a_missing_ad(self):
        # What S3 answers for a missing key when the caller may not list the bucket.
        denied = FakeS3({}, missing="AccessDenied")
        self.assertIsNone(source.reader("s3://bucket/bridge", s3_client=denied)("tampered"))
        down = FakeS3({}, missing="SlowDown")
        with self.assertRaises(FakeS3.ClientError):
            source.reader("s3://bucket/bridge", s3_client=down)(None)

    def test_server_answers_no_ad_when_the_source_is_down(self):
        handler = server.make_handler("http://127.0.0.1:1/bridge", "https://cdn.test/ads")
        handler.log_message = lambda *a: None
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/vast") as r:
            self.assertEqual((r.status, len(ET.fromstring(r.read()))), (200, 0))


class Lambda(unittest.TestCase):
    """The Function URL event in, the same answers as the local server out."""

    def event(self, path, query="", method="GET"):
        return {"rawPath": path, "rawQueryString": query, "requestContext": {"http": {"method": method}}}

    def ask(self, *args, ads=None, **kwargs):
        ads = {None: hand_ids(), "legit": hand_ids()} if ads is None else ads
        with contextlib.redirect_stdout(io.StringIO()):
            return lambda_handler.respond(self.event(*args, **kwargs), ads.get, "https://cdn.test/ad")

    def test_serves_the_default_and_a_named_ad(self):
        for query, name in (("", "default"), ("ad=legit", "legit")):
            response = self.ask("/vast", query)
            self.assertEqual(response["statusCode"], 200)
            self.assertEqual(response["headers"]["Content-Type"], "application/xml; charset=utf-8")
            self.assertEqual(response["headers"]["Access-Control-Allow-Origin"], "*")
            root = ET.fromstring(response["body"])
            self.assertEqual(len(list(root.iter("HandId"))), 3)
            self.assertEqual([f.text for f in root.iter("MediaFile")],
                             [f"https://cdn.test/ad/{name}/ad.mp4", f"https://cdn.test/ad/{name}/index.m3u8"])

    def test_no_bridge_output_means_no_ad(self):
        response = self.ask("/vast", "ad=tampered")
        self.assertEqual((response["statusCode"], len(ET.fromstring(response["body"]))), (200, 0))

    def test_unreadable_source_means_no_ad(self):
        def down(ad):
            raise OSError("S3 is down")
        with contextlib.redirect_stdout(io.StringIO()):
            response = lambda_handler.respond(self.event("/vast"), down, "https://cdn.test/ad")
        self.assertEqual((response["statusCode"], len(ET.fromstring(response["body"]))), (200, 0))

    def test_same_refusals_as_the_local_server(self):
        self.assertEqual(self.ask("/vast", "ad=../secret")["statusCode"], 400)
        self.assertEqual(self.ask("/vast", "ad=")["statusCode"], 200)  # blank value: default ad
        self.assertEqual(self.ask("/other")["statusCode"], 404)
        self.assertEqual(self.ask("/vast", method="POST")["statusCode"], 405)

    def test_handler_reads_its_settings_from_the_environment(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / "hand_ids.json").write_text(json.dumps(hand_ids()), encoding="utf-8")
        self.addCleanup(setattr, lambda_handler, "_read_hand_ids", None)
        with mock.patch.dict(os.environ, {"BRIDGE_OUTPUT": tmp.name, "AD_MEDIA_BASE": "https://cdn.test/ad"}):
            response = lambda_handler.handler(self.event("/vast"), None)
        self.assertEqual(len(list(ET.fromstring(response["body"]).iter("HandId"))), 3)


if __name__ == "__main__":
    unittest.main()
