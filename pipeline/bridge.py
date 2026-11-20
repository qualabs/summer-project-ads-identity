"""
bridge.py

The C2PA -> ad signaling bridge. The same script serves both ad paths;
the only difference is who ends up writing the SVTA2053 into the playlist
the player sees.

  1. Verify the C2PA of the mezzanine. If it fails, nothing comes out.
  2. Extract the HAND IDs (Type 02, Type 04 and whatever else it carries).
  3. Write two files:
     hand_ids.json  the IDs, for the ad server to build the VAST (SSAI path)
     svta2053.json  the SVTA2053 payload (JSON and base64) and the DATERANGE
                    attributes, for whoever writes the playlist: the ad's own
                    playlist (SGAI) or the post-SSAI fix-up

Run it on the mezzanine, before packaging: the re-encode breaks the
signature, so afterwards there is nothing left to verify.

  python pipeline/bridge.py media_src/signed_ad.mp4 [--ad-id QLAB0000001H] [--out out/bridge]

Exit code 2 when the file can't be trusted; any previous output in --out is
removed so nobody picks up stale IDs.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_hand  # noqa: E402
import svta2053  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ("hand_ids.json", "svta2053.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return round(float(out.stdout), 3)
    except ValueError:
        return None


def run(video, ad_id, cfg):
    """Returns (hand_ids, svta). Raises extract_hand.NotTrusted."""
    c2pa = extract_hand.extract(video)
    video = Path(video)
    source = {
        "file": video.name,
        "sha256": sha256(video),
        "duration": duration(video),
        "c2pa": {
            "validation_state": c2pa["validation_state"],
            "signer": c2pa["signer"],
            "untrusted_cert": c2pa["untrusted_cert"],
            "hand_ids_from": c2pa["from"],
        },
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    hand_ids = {
        "ad_id": ad_id,
        "hand": c2pa["hand"],
        "resolver": "https://doi.org/",
        "source": source,
    }
    p = svta2053.payload_for(ad_id, c2pa["hand"], cfg["schemes"])
    b64 = svta2053.encode_checked(p)
    svta = {
        "class": cfg["class"],
        "attribute": svta2053.ATTRIBUTE,
        "payload": p,
        "base64": b64,
        "daterange_attributes": {
            "CLASS": cfg["class"],
            svta2053.ATTRIBUTE: b64,
            "DURATION": source["duration"],
        },
        "note": "Whoever writes the playlist adds ID (unique in that playlist) and "
                "START-DATE (SGAI: the ad playlist's first PROGRAM-DATE-TIME; "
                "SSAI: where the ad landed in the stitched playlist).",
        "source": {"file": video.name, "sha256": source["sha256"]},
    }
    return hand_ids, svta


def write(out_dir, hand_ids, svta):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in zip(OUTPUTS, (hand_ids, svta)):
        (out_dir / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def clear(out_dir):
    for name in OUTPUTS:
        (out_dir / name).unlink(missing_ok=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    ids = json.loads((ROOT / "ids.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="signed mezzanine")
    ap.add_argument("--ad-id", default=ids["ad_id"]["id"], help="Ad-ID of the creative (not in the C2PA)")
    ap.add_argument("--out", default=str(ROOT / "out" / "bridge"))
    args = ap.parse_args()
    out_dir = Path(args.out)

    try:
        hand_ids, svta = run(args.video, args.ad_id, ids["svta2053"])
    except extract_hand.NotTrusted as e:
        clear(out_dir)
        print(f"⛔ {e}. Nothing is written.")
        sys.exit(2)

    write(out_dir, hand_ids, svta)
    c = hand_ids["source"]["c2pa"]
    print(f"✅ C2PA {c['validation_state']}, signed by \"{c['signer']}\"")
    if c["untrusted_cert"]:
        print("⚠️  Test certificate, not on any trust list: in production this would be rejected.")
    for t, v in hand_ids["hand"].items():
        print(f"   {t}  {v}")
    shown = out_dir.resolve()
    shown = shown.relative_to(ROOT) if shown.is_relative_to(ROOT) else shown
    print(f"→ {shown / OUTPUTS[0]}  (ad server → VAST, SSAI path)")
    print(f"→ {shown / OUTPUTS[1]}  (SVTA2053 DATERANGE: the ad playlist in SGAI, or the post-SSAI fix-up)")


if __name__ == "__main__":
    main()
