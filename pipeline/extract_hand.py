"""
extract_hand.py

Reads the HAND IDs out of a C2PA-signed video, before it is packaged
(packaging re-encodes the video and the signature stops matching).
Same logic as puente/puente.mjs from the C2PA exploration, in Python:

  1. c2patool reads the manifest store. No manifest -> fail.
  2. Validation: any failure other than signingCredential.untrusted
     (the c2patool test certificate) -> fail. A changed byte in the
     video shows up here as a hash mismatch.
  3. The org.hand-id.identity assertion, in the active manifest or in
     an ingredient (a re-signed file keeps the original as ingredient).

It does not query the HAND registry: in the demo that check happens in
the player (see the plan in the WG doc).

  python pipeline/extract_hand.py media_src/signed_mezzanine.mp4
Exit code 2 when the file can't be trusted.
"""

import json
import subprocess
import sys

TOLERATED = {"signingCredential.untrusted"}


class NotTrusted(Exception):
    pass


def extract(path):
    try:
        out = subprocess.run(["c2patool", str(path)], capture_output=True, text=True, check=True).stdout
        store = json.loads(out)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        raise NotTrusted("the file has no C2PA manifest (was it already transcoded?)")

    failures = [f["code"] for f in store.get("validation_results", {})
                .get("activeManifest", {}).get("failure", [])]
    serious = [c for c in failures if c not in TOLERATED]
    if serious:
        raise NotTrusted("invalid manifest: " + ", ".join(serious))

    manifests = store["manifests"]
    active = manifests[store["active_manifest"]]

    def chain(label, depth=0):
        m = manifests.get(label)
        if not m:
            return
        yield m, depth
        for ing in m.get("ingredients", []):
            if ing.get("active_manifest"):
                yield from chain(ing["active_manifest"], depth + 1)

    for m, depth in chain(store["active_manifest"]):
        a = next((x for x in m.get("assertions", []) if x["label"] == "org.hand-id.identity"), None)
        if a:
            d = a["data"]
            ids = {"type01": d.get("humanIdentity"),
                   "type02": d.get("licensedHumanLikeness"),
                   "type04": d.get("productionEntity")}
            if not ids["type01"] or not ids["type02"]:
                raise NotTrusted("the org.hand-id.identity assertion does not carry Type 01 and Type 02")
            return {
                "hand": {k: v for k, v in ids.items() if v},
                "from": "active manifest" if depth == 0 else f"ingredient level {depth}",
                "signer": active.get("signature_info", {}).get("issuer"),
                "untrusted_cert": "signingCredential.untrusted" in failures,
                "validation_state": store.get("validation_state"),
            }
    raise NotTrusted("the manifest does not carry the org.hand-id.identity assertion")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    if len(sys.argv) != 2:
        raise SystemExit("usage: python pipeline/extract_hand.py <signed_video.mp4>")
    try:
        r = extract(sys.argv[1])
    except NotTrusted as e:
        print(f"⛔ {e}. No IDs written.")
        sys.exit(2)
    print(json.dumps(r, indent=2, ensure_ascii=False))
