// player.js — one player for both ad paths (CONTRACTS.md contract 3).
//
// The HAND IDs are always in an SVTA2053 EXT-X-DATERANGE; where that
// DATERANGE sits depends on the path:
//   SSAI: in the playlist the player loads (the ad is stitched into it).
//   SGAI: in the ad's own playlist, which hls.js loads in a separate player
//         it creates for each interstitial asset. The main player never sees
//         that playlist, so we hook the asset player.
// Every ad found is passed to onAd(ad). The permission check (HAND registry)
// and the signature check (remote C2PA manifest) plug in there.

import { ATTRIBUTE, byScheme, decode, isSignal } from "./svta2053.js";

export function createPlayer(video, { schemes, onAd, onEvent }) {
  const seen = new Set();
  const event = (text, kind) => onEvent?.(text, kind);

  // Read every SVTA2053 DATERANGE of a loaded playlist
  function readPlaylist(details, path) {
    for (const r of Object.values(details.dateRanges || {})) {
      if (!isSignal(r)) continue;
      const key = `${path}|${details.url}|${r.id}`;
      if (seen.has(key)) continue; // live playlists reload; report each ad once
      seen.add(key);
      let ad;
      try {
        const payload = decode(r.attr[ATTRIBUTE]);
        ad = { path, playlist: details.url, id: r.id, class: r.class,
               start: r.startDate, duration: r.duration,
               payload, ...byScheme(payload.identifiers, schemes) };
      } catch (e) {
        ad = { path, playlist: details.url, id: r.id, class: r.class, error: e.message };
      }
      onAd(ad);
    }
  }

  const hls = new Hls({ enableDateRangeMetadataCues: true });

  // SSAI (or an ad playlist loaded directly): the DATERANGE is in this playlist
  hls.on(Hls.Events.LEVEL_LOADED, (_, { details }) => readPlaylist(details, "main playlist"));

  // SGAI: interstitials
  hls.on(Hls.Events.ASSET_LIST_LOADED, (_, d) => {
    event(`Asset list loaded (${d.assetListResponse?.ASSETS?.length ?? 0} asset(s)). ` +
          "No HAND IDs expected here.");
  });
  hls.on(Hls.Events.INTERSTITIAL_ASSET_PLAYER_CREATED, (_, d) => {
    const assetHls = d.player?.hls;
    event(`Interstitial asset player created for ${d.asset?.uri ?? "?"}`, "ad");
    assetHls?.on(Hls.Events.LEVEL_LOADED, (_, { details }) =>
      readPlaylist(details, "interstitial asset (SGAI)"));
  });
  hls.on(Hls.Events.INTERSTITIAL_STARTED, () => event("Interstitial started", "ad"));
  hls.on(Hls.Events.INTERSTITIAL_ENDED, () => event("Interstitial ended, back to content"));
  hls.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) event(`Fatal error: ${d.details}`, "bad"); });

  // When an ad's DATERANGE is reached during playback
  const hooked = new WeakSet();
  const hook = (track) => {
    if (track.kind !== "metadata" || hooked.has(track)) return;
    hooked.add(track);
    track.mode = "hidden";
    track.addEventListener("cuechange", () => {
      for (const c of track.activeCues || []) {
        if (c.__seen || c.value?.key !== ATTRIBUTE) continue;
        c.__seen = true;
        event("Ad DATERANGE reached in playback", "ad");
      }
    });
  };
  Array.from(video.textTracks).forEach(hook);
  video.textTracks.addEventListener("addtrack", (e) => hook(e.track));

  return {
    load(src) {
      seen.clear();
      // Attach first: hls.js only turns DATERANGEs into cues if the media is
      // attached when the playlist arrives.
      hls.once(Hls.Events.MEDIA_ATTACHED, () => hls.loadSource(src));
      hls.attachMedia(video);
    },
    hls,
  };
}
