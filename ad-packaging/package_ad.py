"""
package_ad.py

Packages the signed mezzanine as an HLS ad, in two versions, served from one
place (out/ad/ by default):

  legit/index.m3u8     the ad's own playlist with the SVTA2053
                       EXT-X-DATERANGE written from the bridge output
                       (svta2053.json), as CONTRACTS.md contract 3 says
  legit/ad.mp4         the same encode as one MP4 (what MediaTailor takes)
  tampered/index.m3u8  the same segments, but the DATERANGE carries one
                       changed HAND ID: what an attacker on the path would
                       do. The player has to flag it.
  tampered/ad.mp4      the same MP4
  default/             the legit ad again, for GET /vast without ?ad=

That is the layout the ad server (adserver/) builds its MediaFile URLs from:
<media-base>/<name>/ad.mp4 and <media-base>/<name>/index.m3u8, reading
out/bridge/hand_ids.json for the default ad and out/bridge/<name>/hand_ids.json
for a named one. Every name carries the legit IDs: the attack changes the
playlist, not the VAST.

The bridge output is written last, once the packaging is complete. If
anything fails (an invalid signature, the encode), the bridge output and the
packaged folders are removed: the ad server then answers an empty VAST.

  python ad-packaging/package_ad.py <signed mezzanine> [--tamper type04] [--out out/ad]

Needs c2patool, ffmpeg and ffprobe on the PATH.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import bridge  # noqa: E402
import extract_hand  # noqa: E402
import svta2053  # noqa: E402

# The ad playlist's own timeline. SVTA2053 needs EXT-X-PROGRAM-DATE-TIME, also
# in VOD; any fixed date works. START-DATE is this same instant (contract 3).
PDT = "2026-01-01T00:00:00.000Z"
SEGMENT_SECONDS = 4
EVENT_ID = "ad-1"
VERSIONS = ("legit", "tampered")  # the ad server's ?ad=<name>
DEFAULT = "default"                # the ad server's name when no ?ad= is given


def encode(src, out_dir):
    """
    Re-encode once to a 720p MP4 (ad.mp4) with a keyframe every segment, then
    cut that same MP4 into HLS segments without re-encoding.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4 = out_dir / "ad.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_SECONDS})",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(mp4),
    ], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-c", "copy",
        "-f", "hls", "-hls_time", str(SEGMENT_SECONDS), "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(out_dir / "seg_%03d.ts"),
        str(out_dir / "index.m3u8"),
    ], check=True)


def clear_outputs(bridge_dir, out):
    """
    Nothing servable may be left behind: no bridge output, no packaging.
    Only what this script writes is removed, never the whole --out folder.
    """
    bridge.clear(bridge_dir)
    for v in VERSIONS:
        bridge.clear(bridge_dir / v)
    for v in (*VERSIONS, DEFAULT):
        shutil.rmtree(out / v, ignore_errors=True)
    (out / "ad.json").unlink(missing_ok=True)


def link_or_copy(src, dst):
    """Same file under another name; a copy where hard links don't work."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def write_bridge_output(bridge_dir, hand_ids, svta):
    """
    out/bridge/ for the default ad (and the other pieces' defaults), and only
    hand_ids.json in out/bridge/<version>/: it is all the ad server reads, and
    a svta2053.json there would not match the tampered playlist.
    """
    bridge.write(bridge_dir, hand_ids, svta)
    for v in VERSIONS:
        d = bridge_dir / v
        d.mkdir(parents=True, exist_ok=True)
        (d / "hand_ids.json").write_text(
            json.dumps(hand_ids, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def with_daterange(playlist_text, daterange, segment_prefix=""):
    """
    Put one EXT-X-PROGRAM-DATE-TIME and the DATERANGE before the first segment.
    segment_prefix lets another playlist point at the legit segments.
    """
    out, placed = [], False
    for line in playlist_text.splitlines():
        if line.startswith("#EXT-X-PROGRAM-DATE-TIME"):
            continue
        if line.startswith("#EXTINF") and not placed:
            out += [f"#EXT-X-PROGRAM-DATE-TIME:{PDT}", daterange]
            placed = True
        if line and not line.startswith("#"):
            line = segment_prefix + line
        out.append(line)
    return "\n".join(out) + "\n"


def tampered_id(value):
    """A different, well-formed HAND ID: flip the last group of the suffix."""
    prefix, _, last = value.rpartition("-")
    flipped = "".join("0" if c != "0" else "F" for c in last)
    return f"{prefix}-{flipped}"


def package(args, ids, out, hand_ids, attrs):
    """Encode and write every playlist. Returns the tampered HAND IDs and the original value."""
    # 2. Encode once
    legit = out / "legit"
    encode(args.mezzanine, legit)
    raw = (legit / "index.m3u8").read_text()

    # 3. Legit: the bridge's attributes as they are, plus ID and START-DATE
    line = svta2053.daterange_line(EVENT_ID, PDT, attrs["DURATION"],
                                   attrs[svta2053.ATTRIBUTE], attrs["CLASS"])
    (legit / "index.m3u8").write_text(with_daterange(raw, line))

    # 4. Tampered: same segments, one HAND ID changed in the payload
    hand = dict(hand_ids["hand"])
    original = hand[args.tamper]
    hand[args.tamper] = tampered_id(original)
    bad_b64 = svta2053.encode_checked(
        svta2053.payload_for(args.ad_id, hand, ids["svta2053"]["schemes"]))
    bad_line = svta2053.daterange_line(EVENT_ID, PDT, attrs["DURATION"], bad_b64, attrs["CLASS"])
    tampered = out / "tampered"
    tampered.mkdir()
    link_or_copy(legit / "ad.mp4", tampered / "ad.mp4")
    (tampered / "index.m3u8").write_text(with_daterange(raw, bad_line, segment_prefix="../legit/"))

    # 5. Default: the legit ad under the ad server's default name
    default = out / DEFAULT
    default.mkdir()
    link_or_copy(legit / "ad.mp4", default / "ad.mp4")
    (default / "index.m3u8").write_text(with_daterange(raw, line, segment_prefix="../legit/"))

    (out / "ad.json").write_text(json.dumps({
        "mezzanine": hand_ids["source"]["file"],
        "sha256": hand_ids["source"]["sha256"],
        "duration": attrs["DURATION"],
        "legit": {"playlist": "legit/index.m3u8", "mp4": "legit/ad.mp4", "hand": hand_ids["hand"]},
        "tampered": {"playlist": "tampered/index.m3u8", "mp4": "tampered/ad.mp4",
                     "changed": args.tamper,
                     "from": original, "to": hand[args.tamper]},
        "default": {"same_as": "legit"},
    }, indent=2) + "\n", encoding="utf-8")
    return hand, original


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    ids = json.loads((ROOT / "ids.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser()
    ap.add_argument("mezzanine", help="signed mezzanine (C2PA with org.hand-id.identity)")
    ap.add_argument("--ad-id", default=ids["ad_id"]["id"])
    ap.add_argument("--tamper", default="type04", choices=["type01", "type02", "type04"],
                    help="which HAND ID the tampered version changes")
    ap.add_argument("--out", default=str(ROOT / "out" / "ad"))
    args = ap.parse_args()
    out = Path(args.out)
    bridge_dir = ROOT / "out" / "bridge"

    # 1. Bridge: verify and extract before encoding (the re-encode breaks the signature)
    try:
        hand_ids, svta = bridge.run(args.mezzanine, args.ad_id, ids["svta2053"])
    except extract_hand.NotTrusted as e:
        clear_outputs(bridge_dir, out)
        print(f"⛔ {e}. Nothing packaged: this ad must not be served.")
        sys.exit(2)
    attrs = svta["daterange_attributes"]
    if args.tamper not in hand_ids["hand"]:
        clear_outputs(bridge_dir, out)
        sys.exit(f"the manifest has no {args.tamper} to tamper with. Nothing packaged.")
    if not attrs.get("DURATION"):
        clear_outputs(bridge_dir, out)
        sys.exit("the bridge could not read the duration. Nothing packaged.")

    # Remove the previous run first: until the end, nothing is servable
    clear_outputs(bridge_dir, out)
    try:
        hand, original = package(args, ids, out, hand_ids, attrs)
    except BaseException:
        clear_outputs(bridge_dir, out)
        print("⛔ Packaging failed. Nothing packaged: this ad must not be served.")
        raise

    # 6. Last: the bridge output is what makes the ad servable
    write_bridge_output(bridge_dir, hand_ids, svta)

    c = hand_ids["source"]["c2pa"]
    print(f"✅ C2PA {c['validation_state']}, signed by \"{c['signer']}\"")
    if c["untrusted_cert"]:
        print("⚠️  Test certificate, not in any trust list: production would reject it.")
    n = sum(1 for l in (out / "legit" / "index.m3u8").read_text().splitlines() if l.endswith(".ts"))
    print(f"→ {out / 'legit' / 'index.m3u8'}  ({n} segments, {attrs['DURATION']} s)")
    print(f"→ {out / 'tampered' / 'index.m3u8'}  ({args.tamper}: {original} → {hand[args.tamper]})")
    print(f"→ {out / DEFAULT / 'index.m3u8'}  (the legit ad, for GET /vast without ?ad=)")


if __name__ == "__main__":
    main()
