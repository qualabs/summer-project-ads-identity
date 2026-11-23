"""
package_ad.py

Packages the signed mezzanine as an HLS ad, in two versions, served from one
place (out/ad/ by default):

  legit/index.m3u8     the ad's own playlist with the SVTA2053
                       EXT-X-DATERANGE written from the bridge output
                       (svta2053.json), as CONTRACTS.md contract 3 says
  tampered/index.m3u8  the same segments, but the DATERANGE carries one
                       changed HAND ID: what an attacker on the path would
                       do. The player has to flag it.

The other tampering case, a mezzanine with no valid signature, never gets
here: the bridge refuses it (exit code 2) and nothing is packaged.

  python ad-packaging/package_ad.py <signed mezzanine> [--tamper type04] [--out out/ad]

Needs c2patool, ffmpeg and ffprobe on the PATH.
"""

import argparse
import json
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


def encode_hls(src, out_dir):
    """Re-encode to a streaming rendition and cut it into segments."""
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_SECONDS})",
        "-c:a", "aac", "-b:a", "128k",
        "-f", "hls", "-hls_time", str(SEGMENT_SECONDS), "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(out_dir / "seg_%03d.ts"),
        str(out_dir / "index.m3u8"),
    ], check=True)


def with_daterange(playlist_text, daterange, segment_prefix=""):
    """
    Put one EXT-X-PROGRAM-DATE-TIME and the DATERANGE before the first segment.
    segment_prefix lets the tampered playlist point at the legit segments.
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

    # 1. Bridge: verify and extract before encoding (the re-encode breaks the signature)
    bridge_dir = ROOT / "out" / "bridge"
    try:
        hand_ids, svta = bridge.run(args.mezzanine, args.ad_id, ids["svta2053"])
    except extract_hand.NotTrusted as e:
        # Remove any earlier packaging too: nothing servable may be left behind
        bridge.clear(bridge_dir)
        shutil.rmtree(out, ignore_errors=True)
        print(f"⛔ {e}. Nothing packaged: this ad must not be served.")
        sys.exit(2)
    if args.tamper not in hand_ids["hand"]:
        # Same rule: no earlier packaging left behind
        bridge.clear(bridge_dir)
        shutil.rmtree(out, ignore_errors=True)
        sys.exit(f"the manifest has no {args.tamper} to tamper with. Nothing packaged.")
    bridge.write(bridge_dir, hand_ids, svta)

    # 2. Encode once
    if out.exists():
        shutil.rmtree(out)
    legit = out / "legit"
    encode_hls(args.mezzanine, legit)
    raw = (legit / "index.m3u8").read_text()
    attrs = svta["daterange_attributes"]

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
    (tampered / "index.m3u8").write_text(with_daterange(raw, bad_line, segment_prefix="../legit/"))

    (out / "ad.json").write_text(json.dumps({
        "mezzanine": hand_ids["source"]["file"],
        "sha256": hand_ids["source"]["sha256"],
        "duration": attrs["DURATION"],
        "legit": {"playlist": "legit/index.m3u8", "hand": hand_ids["hand"]},
        "tampered": {"playlist": "tampered/index.m3u8", "changed": args.tamper,
                     "from": original, "to": hand[args.tamper]},
    }, indent=2) + "\n", encoding="utf-8")

    c = hand_ids["source"]["c2pa"]
    print(f"✅ C2PA {c['validation_state']}, signed by \"{c['signer']}\"")
    if c["untrusted_cert"]:
        print("⚠️  Test certificate, not in any trust list: production would reject it.")
    n = sum(1 for l in raw.splitlines() if l.endswith(".ts"))
    print(f"→ {out / 'legit' / 'index.m3u8'}  ({n} segments, {attrs['DURATION']} s)")
    print(f"→ {out / 'tampered' / 'index.m3u8'}  ({args.tamper}: {original} → {hand[args.tamper]})")


if __name__ == "__main__":
    main()
