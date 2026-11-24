"""
vast.py

Builds the VAST the ad server returns (contract 2 in CONTRACTS.md) from the
hand_ids.json the bridge wrote. It never opens the video: everything about
the ad comes from that JSON, and the media URLs from the caller.

  build(hand_ids, media)  the VAST for one verified ad
  empty()                 the VAST for "no ad": what we answer when the bridge
                          left no output, so the ad must not be served
"""

import xml.etree.ElementTree as ET

VERSION = "4.2"
AD_SYSTEM = "ads-identity-demo"
AD_ID_REGISTRY = "ad-id.org"
EXTENSION_TYPE = "hand-id"
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'


def duration(seconds):
    """78.047 -> "00:01:18.047" (HH:MM:SS.mmm). Not rounded to whole seconds:
    vast-2-sgai copies it into the asset list's DURATION, and a rounded value
    can be longer than the ad."""
    ms = int(round(seconds * 1000))
    total, ms = divmod(ms, 1000)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}.{ms:03d}"


def hand_type(key):
    """"type02" -> "02"."""
    if not key.startswith("type") or not key[4:].isdigit():
        raise ValueError(f"unexpected HAND ID key: {key}")
    return key[4:]


def _serialize(root):
    ET.indent(root, space="  ")
    return XML_DECLARATION + ET.tostring(root, encoding="unicode") + "\n"


def empty():
    return _serialize(ET.Element("VAST", version=VERSION))


def build(hand_ids, media):
    """
    hand_ids  the parsed hand_ids.json
    media     {"mp4": url, "hls": url, "width": int, "height": int}
    """
    ad_id = hand_ids["ad_id"]
    hand = hand_ids["hand"]
    for required in ("type01", "type02"):
        if not hand.get(required):
            raise ValueError(f"hand_ids.json has no {required}")
    seconds = hand_ids["source"]["duration"]
    if not seconds:
        raise ValueError("hand_ids.json has no duration")
    size = {"width": str(media["width"]), "height": str(media["height"])}

    root = ET.Element("VAST", version=VERSION)
    inline = ET.SubElement(ET.SubElement(root, "Ad", id=ad_id), "InLine")
    ET.SubElement(inline, "AdSystem").text = AD_SYSTEM
    ET.SubElement(inline, "AdTitle").text = f"HAND ID demo ad {ad_id}"

    creative = ET.SubElement(ET.SubElement(inline, "Creatives"), "Creative")
    ET.SubElement(creative, "UniversalAdId", idRegistry=AD_ID_REGISTRY).text = ad_id
    linear = ET.SubElement(creative, "Linear")
    ET.SubElement(linear, "Duration").text = duration(seconds)
    files = ET.SubElement(linear, "MediaFiles")
    ET.SubElement(files, "MediaFile", delivery="progressive", type="video/mp4", **size).text = media["mp4"]
    ET.SubElement(files, "MediaFile", delivery="streaming", type="application/x-mpegURL", **size).text = media["hls"]

    extension = ET.SubElement(ET.SubElement(inline, "Extensions"), "Extension", type=EXTENSION_TYPE)
    for key in sorted(hand):
        ET.SubElement(extension, "HandId", type=hand_type(key)).text = hand_ids["resolver"] + hand[key]

    return _serialize(root)
