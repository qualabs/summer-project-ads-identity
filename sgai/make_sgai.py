"""
make_sgai.py

Writes the content playlists of the SGAI path: the content's media playlist,
unchanged, plus one HLS Interstitial at each ad break, pointing at
vast-2-sgai. One playlist per ad, since the ad is chosen in the VAST URL:

  out/sgai/legit.m3u8      ...?vasturl=<ad server>/vast?ad=legit
  out/sgai/tampered.m3u8   ...?vasturl=<ad server>/vast?ad=tampered

The interstitial goes right after the break's SCTE35-OUT EXT-X-DATERANGE
(content/make_stream.py), with the same START-DATE and DURATION:

  #EXT-X-DATERANGE:ID="break-1-sgai",CLASS="com.apple.hls.interstitial",
    START-DATE="...",DURATION=78.083,X-ASSET-LIST="...",X-RESUME-OFFSET=78.083

X-RESUME-OFFSET is the break's duration, not the ad's: after the ad the player
resumes past the colour bars. The playlist carries no HAND IDs (contract 3):
they are in the ad's own playlist, which the asset list points to.

  python sgai/make_sgai.py <content media playlist, path or URL>
      --vast2sgai <vast-2-sgai URL> --vast <ad server /vast URL>
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote, urljoin

ATTRIBUTE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')
INTERSTITIAL = "com.apple.hls.interstitial"
ADS = ["legit", "tampered"]


def attributes(line):
    """The attribute list of a tag as a dict, without the quotes."""
    return {k: v.strip('"') for k, v in ATTRIBUTE.findall(line.split(":", 1)[1])}


def asset_list_url(vast2sgai, vast, ad):
    """vast-2-sgai's asset list for one ad. The VAST URL travels percent-encoded in vasturl."""
    vast_for_ad = f"{vast}{'&' if '?' in vast else '?'}ad={quote(ad)}"
    return f"{vast2sgai.rstrip('/')}/api/asset-list?vasturl={quote(vast_for_ad, safe='')}"


def interstitial(break_tag, asset_list):
    """The interstitial for one break, from the break's SCTE35-OUT tag."""
    a = attributes(break_tag)
    duration = float(a["DURATION"])
    return (
        f'#EXT-X-DATERANGE:ID="{a["ID"]}-sgai",CLASS="{INTERSTITIAL}",'
        f'START-DATE="{a["START-DATE"]}",DURATION={duration:.3f},'
        f'X-ASSET-LIST="{asset_list}",X-RESUME-OFFSET={duration:.3f}'
    )


def segment_uri(base, uri):
    """A relative segment URI, seen from the new playlist. urljoin for a URL
    base; a relative base is put in front as it is (urljoin drops a leading ../)."""
    if not base or "://" in uri or uri.startswith("/"):
        return uri
    return urljoin(base, uri) if "://" in base else base + uri


def sgai_playlist(content, asset_list, segments_base=""):
    """
    content: the content's media playlist (text).
    asset_list: the X-ASSET-LIST URL for every break.
    segments_base: where the segments are, seen from the new playlist, so it
                   can live somewhere else than the segments.
    """
    if not content.startswith("#EXTM3U") or "#EXT-X-PROGRAM-DATE-TIME:" not in content:
        raise ValueError("not a media playlist with EXT-X-PROGRAM-DATE-TIME")
    out, breaks = [], 0
    for line in content.splitlines():
        if line.startswith("#EXT-X-DATERANGE:") and INTERSTITIAL in line:
            raise ValueError("the content playlist already has an interstitial")
        if line and not line.startswith("#"):
            line = segment_uri(segments_base, line)
        out.append(line)
        if line.startswith("#EXT-X-DATERANGE:") and "SCTE35-OUT=" in line:
            a = attributes(line)
            if "DURATION" not in a or "START-DATE" not in a:
                raise ValueError(f'break {a.get("ID", "?")}: no START-DATE or DURATION')
            out.append(interstitial(line, asset_list))
            breaks += 1
    if not breaks:
        raise ValueError("no ad break (EXT-X-DATERANGE with SCTE35-OUT) in the content playlist")
    return "\n".join(out) + "\n"


def read(source):
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as r:
            return r.read().decode("utf-8")
    return Path(source).read_text(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("content", help="the content's media playlist (media.m3u8), a path or a URL")
    ap.add_argument("--vast2sgai", required=True, help="vast-2-sgai's base URL")
    ap.add_argument("--vast", required=True, help="the ad server's /vast URL, without ?ad=")
    ap.add_argument("--ads", nargs="+", default=ADS, help=f"one playlist per ad (default: {' '.join(ADS)})")
    ap.add_argument("--segments", default="../content/",
                    help="where the content's segments are, from the written playlist "
                         "(default ../content/, as on CloudFront); a URL for a local test")
    ap.add_argument("--out", default="out/sgai", help="output folder (default out/sgai)")
    args = ap.parse_args()

    for name, url in (("--vast2sgai", args.vast2sgai), ("--vast", args.vast)):
        if not url.startswith(("http://", "https://")):
            sys.exit(f"{name} must be an http(s) URL")

    content = read(args.content)
    # Build every playlist before writing any: a bad input writes nothing
    playlists = {
        ad: sgai_playlist(content, asset_list_url(args.vast2sgai, args.vast, ad), args.segments)
        for ad in args.ads
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for ad, text in playlists.items():
        path = out / f"{ad}.m3u8"
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{path}  X-ASSET-LIST {asset_list_url(args.vast2sgai, args.vast, ad)}")


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"{e}. Nothing written.")
