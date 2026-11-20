"""
svta2053.py

SVTA2053 (Ad Creative Signaling in DASH and HLS, v1.2) for HLS: one
EXT-X-DATERANGE per creative, with
  CLASS                    = urn:svta:advertising-wg:ad-creative-signaling
                             (the normative value; the spec's own examples
                             say ad-id-signaling, which is wrong)
  START-DATE, DURATION     = where the creative is
  X-AD-CREATIVE-SIGNALING  = base64 of {"version": 1, "identifiers": [...]}
EXT-X-PROGRAM-DATE-TIME is required, also in VOD.

identifiers is a list of {scheme, value}, with no size limit: Ad-ID and
the HAND IDs go side by side. The HAND schemes are provisional (see
ids.json): the spec only gives the Ad-ID one.

The payload itself is built by bridge.py from the HAND IDs it extracts
from the C2PA manifest; this module has no copy of the IDs.

  python pipeline/svta2053.py <base64>   decode an X-AD-CREATIVE-SIGNALING
"""

import base64
import json
import sys

CLASS = "urn:svta:advertising-wg:ad-creative-signaling"
ATTRIBUTE = "X-AD-CREATIVE-SIGNALING"


def payload_for(ad_id, hand, schemes):
    """hand = {"type01": "10.23/...", "type02": ..., "type04": ...}; any present type goes in."""
    idents = [{"scheme": schemes["ad_id"], "value": ad_id}] if ad_id else []
    for t in sorted(hand):
        if t not in schemes:
            raise ValueError(f"no SVTA2053 scheme for {t} in ids.json")
        idents.append({"scheme": schemes[t], "value": hand[t]})
    return {"version": 1, "identifiers": idents}


def encode(obj):
    return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()


def decode(b64):
    obj = json.loads(base64.b64decode(b64))
    if obj.get("version") != 1:
        raise ValueError(f"unsupported version {obj.get('version')}")
    for i in obj["identifiers"]:
        if not i.get("scheme") or not i.get("value"):
            raise ValueError(f"identifier without scheme/value: {i}")
    return obj


def encode_checked(p):
    b64 = encode(p)
    if decode(b64) != p:  # round trip, like hand_scte35.py does
        raise SystemExit("SVTA2053 payload does not round-trip")
    return b64


def daterange_line(event_id, start_iso, duration, b64, cls=CLASS):
    """
    The line whoever writes the playlist adds: the ad's own playlist (SGAI,
    START-DATE = its first PROGRAM-DATE-TIME) or the stitched one after SSAI
    (START-DATE = where the ad landed). The ID is unique in the playlist,
    not the ad ID (that goes in the JSON).
    """
    return (
        "#EXT-X-DATERANGE:"
        f'ID="{event_id}",CLASS="{cls}",'
        f'START-DATE="{start_iso}",DURATION={duration:.3f},'
        f'X-AD-CREATIVE-SIGNALING="{b64}"'
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python pipeline/svta2053.py <base64>")
    print(json.dumps(decode(sys.argv[1]), indent=2))
