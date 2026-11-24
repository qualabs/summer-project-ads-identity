"""
server.py

The ad server of the demo: one endpoint that answers "which ad goes in this
break?" with a VAST. MediaTailor (SSAI) and vast-2-sgai (SGAI) call the same
URL and get the same VAST.

  GET /vast            the ad in <bridge-output>/hand_ids.json
  GET /vast?ad=<name>  the ad in <bridge-output>/<name>/hand_ids.json
                       (run the bridge with --out out/bridge/<name>)

It reads only what the bridge wrote. If there is no hand_ids.json for the ad,
the bridge did not trust the file (or never ran): the answer is an empty VAST,
never the ad without its IDs.

  python adserver/server.py [--port 8080] [--bridge-output out/bridge]
                            [--media-base http://localhost:8090/out/ad]

<bridge-output> is where the bridge output lives: a local folder, an
http(s):// base URL or an s3://bucket/prefix (see source.py). BRIDGE_OUTPUT
sets the same thing, so a deployed server needs no local files.

The media URLs are <media-base>/<name>/ad.mp4 and <media-base>/<name>/index.m3u8
(<name> is "default" when no ad is given). AD_MEDIA_BASE sets the same thing.
"""

import argparse
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import source  # noqa: E402
import vast  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AD_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_AD = "default"
WIDTH, HEIGHT = 1280, 720  # the packaged ad (720p), same as the content stream


def vast_for(read_hand_ids, media_base, ad):
    """read_hand_ids is a source.reader. Returns (xml, served)."""
    hand_ids = read_hand_ids(ad)
    if hand_ids is None:
        return vast.empty(), False
    base = f"{media_base.rstrip('/')}/{ad or DEFAULT_AD}"
    media = {"mp4": f"{base}/ad.mp4", "hls": f"{base}/index.m3u8", "width": WIDTH, "height": HEIGHT}
    return vast.build(hand_ids, media), True


def make_handler(bridge_output, media_base):
    """bridge_output: a location source.reader understands, or a reader itself."""
    read_hand_ids = bridge_output if callable(bridge_output) else source.reader(bridge_output)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path != "/vast":
                return self.send(404, "not found\n", "text/plain; charset=utf-8")
            ad = parse_qs(url.query).get("ad", [None])[0]
            if ad is not None and not AD_NAME.match(ad):
                return self.send(400, "invalid ad name\n", "text/plain; charset=utf-8")
            try:
                xml, served = vast_for(read_hand_ids, media_base, ad)
            except Exception as e:
                # A hand_ids.json we can't read (remote source down) or can't
                # turn into the contract's VAST is not a verified ad either:
                # answer "no ad" and say why in the log.
                self.log_message("unusable hand_ids.json for ad=%s: %r", ad, e)
                xml, served = vast.empty(), False
            if not served:
                self.log_message("no bridge output for ad=%s: empty VAST", ad)
            self.send(200, xml, "application/xml; charset=utf-8")

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--bridge-output", "--bridge-dir", dest="bridge_output",
                    default=os.environ.get("BRIDGE_OUTPUT", str(ROOT / "out" / "bridge")),
                    help="local folder, http(s):// base URL or s3://bucket/prefix")
    ap.add_argument("--media-base", default=os.environ.get("AD_MEDIA_BASE", "http://localhost:8090/out/ad"))
    args = ap.parse_args()

    handler = make_handler(args.bridge_output, args.media_base)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"ad server on http://127.0.0.1:{args.port}/vast  (bridge output: {args.bridge_output})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
