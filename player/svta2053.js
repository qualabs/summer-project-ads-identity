// svta2053.js — reads the SVTA2053 signal of CONTRACTS.md contract 3.
//
// An EXT-X-DATERANGE whose CLASS is one of CLASSES carries the payload in
// X-AD-CREATIVE-SIGNALING: base64 of {"version": 1, "identifiers": [...]}.
// Identifiers are matched by scheme, never by position; unknown schemes are
// ignored (contract 3), and a scheme that appears twice makes the payload
// unreadable rather than picking one value. The HAND schemes come from ids.json (nothing here
// hardcodes them).

// Both CLASS values are accepted until we know what MediaTailor emits:
// the normative one (what we write) and the one in the spec's examples.
export const CLASSES = [
  "urn:svta:advertising-wg:ad-creative-signaling",
  "urn:svta:advertising-wg:ad-id-signaling",
];
export const ATTRIBUTE = "X-AD-CREATIVE-SIGNALING";

export function isSignal(dateRange) {
  return CLASSES.includes(dateRange.class) && Boolean(dateRange.attr?.[ATTRIBUTE]);
}

// Decode one payload. Throws on anything that isn't a version 1 payload with
// identifiers: vast-2-sgai's asset list uses the same attribute name for a
// version 2 tracking object, which is not this signal.
export function decode(b64) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const obj = JSON.parse(new TextDecoder().decode(bytes));
  if (obj.version !== 1 || !Array.isArray(obj.identifiers)) {
    throw new Error(`not a version 1 payload with identifiers (version ${obj.version})`);
  }
  for (const i of obj.identifiers) {
    if (!i.scheme || !i.value) throw new Error("identifier without scheme or value");
  }
  return obj;
}

// schemes: ids.json's svta2053.schemes, e.g. {ad_id: "urn:smpte:…", type01: "urn:hand-id:type01"}
// Returns {adId, hand: {type01, type02, type04}}. Throws on a repeated scheme:
// the permission check must not run on an ID chosen arbitrarily.
export function byScheme(identifiers, schemes) {
  const kindOf = Object.fromEntries(Object.entries(schemes).map(([k, v]) => [v, k]));
  const out = { adId: null, hand: {} };
  const seen = new Set();
  for (const { scheme, value } of identifiers) {
    if (seen.has(scheme)) throw new Error(`scheme ${scheme} appears more than once`);
    seen.add(scheme);
    const kind = kindOf[scheme];
    if (kind === "ad_id") out.adId = value;
    else if (kind?.startsWith("type")) out.hand[kind] = value;
  }
  return out;
}
