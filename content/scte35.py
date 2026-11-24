"""
scte35.py

The SCTE-35 of the content's ad break, built with threefive: a time_signal
with one segmentation descriptor,

  0x34  Provider Placement Opportunity Start, with the break duration
  0x35  Provider Placement Opportunity End

Both carry the same segmentation_event_id, which is how a reader pairs them.
They only mark the break: no UPID, no HAND IDs (CONTRACTS.md, contract 3).

  python content/scte35.py <hex or base64>   decode a cue
"""

import json
import sys

from threefive import Cue, SegmentationDescriptor, TimeSignal

PLACEMENT_OPPORTUNITY_START = 0x34
PLACEMENT_OPPORTUNITY_END = 0x35


def _cue(type_id, event_id, pts, duration=None):
    signal = TimeSignal()
    signal.time_specified_flag = True
    signal.pts_time = round(pts, 6)

    d = SegmentationDescriptor()
    d.segmentation_event_id = hex(event_id)
    d.segmentation_event_cancel_indicator = False
    d.segmentation_event_id_compliance_indicator = True
    d.program_segmentation_flag = True
    d.delivery_not_restricted_flag = True
    d.segmentation_duration_flag = duration is not None
    if duration is not None:
        d.segmentation_duration = round(duration, 6)
    d.segmentation_upid_type = 0
    d.segmentation_upid_length = 0
    d.segmentation_type_id = type_id
    d.segment_num = 0
    d.segments_expected = 0

    cue = Cue()
    cue.command = signal
    cue.descriptors = [d]
    cue.encode()
    return cue


def placement_start(event_id, pts, duration):
    """0x34 at pts (seconds), announcing a break of `duration` seconds. Returns the HLS hex form."""
    return _checked(_cue(PLACEMENT_OPPORTUNITY_START, event_id, pts, duration),
                    PLACEMENT_OPPORTUNITY_START)


def placement_end(event_id, pts):
    """0x35 at pts (seconds), closing the break opened with the same event_id."""
    return _checked(_cue(PLACEMENT_OPPORTUNITY_END, event_id, pts), PLACEMENT_OPPORTUNITY_END)


def _checked(cue, type_id):
    """Round trip, like svta2053.encode_checked: never write a cue we can't read back."""
    hexed = cue.hex()  # 0xFC30...: the form HLS wants in SCTE35-OUT / SCTE35-IN
    if decode(hexed)["segmentation_type_id"] != type_id:
        raise SystemExit("SCTE-35 cue does not round-trip")
    return hexed.upper().replace("0X", "0x")


def decode(data):
    """What the tests and the README check: type, event id, PTS and duration of a cue."""
    cue = Cue(data)
    if not cue.decode():
        raise ValueError("not a SCTE-35 cue")
    got = cue.get()
    d = got["descriptors"][0]
    return {
        "command": got["command"]["name"],
        "pts_time": got["command"].get("pts_time"),
        "segmentation_type_id": d["segmentation_type_id"],
        "segmentation_message": d["segmentation_message"],
        "segmentation_event_id": int(d["segmentation_event_id"], 16),
        "segmentation_duration": d.get("segmentation_duration"),
        "upid_length": d["segmentation_upid_length"],
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python content/scte35.py <hex or base64>")
    print(json.dumps(decode(sys.argv[1]), indent=2))
