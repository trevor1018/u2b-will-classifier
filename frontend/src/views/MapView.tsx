import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet.markercluster";
import { Globe2 } from "lucide-react";
import { useStore, useFilteredCases } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, STATUS_LABEL } from "../lib/types";
import type { CaseRecord } from "../lib/types";
import { COUNTRY_GEO } from "../lib/countryGeo";

// Some cases share an identical lat/lon (country-centroid fallback when the
// LLM didn't extract a city). Stacked points never separate at any zoom, so
// the user only sees the cluster icon and a synthetic "spiderfy" fan that
// looks unrelated to real geography.
//
// Compute deterministic display coords: cases that share a position get
// distributed on a small circle around it (radius scales with √count, so
// 21 cases on the US centroid spread across ~75km, still inside the
// country). Single-point cases keep their real coords.
function buildDisplayCoords(
  allCases: CaseRecord[],
): Map<string, [number, number]> {
  const groups = new Map<string, CaseRecord[]>();
  for (const c of allCases) {
    if (c.lat == null || c.lon == null) continue;
    // ~1km bucket. Cases within 1km of each other share a key and get
    // visually separated by jitter, otherwise their exact distinct coords
    // are kept. Solves both extremes:
    //   - LLM gave the same city-centre to many cases → all in one bucket,
    //     spread out so each is clickable
    //   - Two cases at slightly-different coords <1km apart (e.g. both at
    //     Itaewon — 270m apart in the real data) still get jittered apart
    //     enough to not visually occlude each other at country zoom
    const key = `${c.lat.toFixed(2)},${c.lon.toFixed(2)}`;
    let arr = groups.get(key);
    if (!arr) {
      arr = [];
      groups.set(key, arr);
    }
    arr.push(c);
  }
  const out = new Map<string, [number, number]>();
  for (const [key, group] of groups) {
    if (group.length === 1) {
      out.set(group[0].id, [group[0].lat!, group[0].lon!]);
      continue;
    }
    // Sort by id so positions are stable across filter changes
    group.sort((a, b) => a.id.localeCompare(b.id));
    const [baseLat, baseLon] = key.split(",").map(Number);
    // Tighter than the previous 0.15·√n. With 0.07: n=2 → 0.10° (≈11km),
    // n=12 → 0.24° (≈27km), n=21 → 0.32° (≈36km). Big enough to be
    // visibly separated at country zoom (≥6) but always inside the
    // country, never flung out to a neighbour.
    const radius = Math.min(0.4, 0.07 * Math.sqrt(group.length));
    for (let i = 0; i < group.length; i++) {
      const angle = (i * 2 * Math.PI) / group.length;
      out.set(group[i].id, [
        baseLat + radius * Math.sin(angle),
        // Compensate longitude for latitude (1°lon shrinks at high lat)
        baseLon + (radius * Math.cos(angle)) / Math.max(0.2, Math.cos((baseLat * Math.PI) / 180)),
      ]);
    }
  }
  return out;
}

// Strategy stack (top = applied first):
//
//  1. Imperative Leaflet, not 400+ react-leaflet components
//  2. markerClusterGroup with chunkedLoading + bulk addLayers / removeLayers
//  3. *Diff & patch*: keep a Map<id, marker>; on filter change we only
//     create/destroy the delta. 日本(115) → all(454) becomes "add 339"
//     instead of "destroy 115 + create 454 from scratch".
//  4. Lazy tooltip — HTML is built only when the user actually hovers
//  5. Defer the patch to next animation frame so the click → store
//     update → render path returns immediately (UI feels snappy even
//     while clustering recomputes)
export function MapView() {
  const cases = useFilteredCases();
  // Use ALL cases (not filtered) for jitter computation so a case's display
  // position stays stable regardless of which others are currently visible.
  const allCases = useStore((s) => s.cases);
  const country = useStore((s) => s.country);
  const focus = useStore((s) => s.focusCase);
  const focusRef = useRef(focus);
  focusRef.current = focus;

  const displayCoords = useMemo(
    () => buildDisplayCoords(allCases),
    [allCases],
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const clusterRef = useRef<any>(null);
  // Persistent {video id → marker} so we can patch instead of rebuild.
  const markerMapRef = useRef<Map<string, L.CircleMarker>>(new Map());

  // Init once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [20, 0],
      zoom: 2,
      minZoom: 2,
      worldCopyJump: false,
      maxBounds: L.latLngBounds([-85, -210], [85, 210]),
      maxBoundsViscosity: 1.0,
      preferCanvas: true,
      zoomControl: true,
    });
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: "abcd",
      },
    ).addTo(map);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cluster = (L as any).markerClusterGroup({
      maxClusterRadius: 40,
      showCoverageOnHover: false,
      // No spiderfy: jittered display coords already separate stacked
      // points naturally as the user zooms in.
      spiderfyOnMaxZoom: false,
      // At country-zoom and beyond, every marker is shown individually.
      // (zoomToBoundsOnClick still kicks in at lower zooms when a cluster
      // is clicked, so the experience is: click cluster → zoom in → dots.)
      disableClusteringAtZoom: 6,
      chunkedLoading: true,
      removeOutsideVisibleBounds: true,
      iconCreateFunction: (cluster: { getChildCount: () => number }) => {
        const n = cluster.getChildCount();
        const size = n < 10 ? 30 : n < 50 ? 36 : n < 200 ? 44 : 52;
        return L.divIcon({
          html: `<div class="u2b-cluster"><span>${n}</span></div>`,
          className: "u2b-cluster-wrap",
          iconSize: L.point(size, size),
        });
      },
    });
    cluster.addTo(map);

    mapRef.current = map;
    clusterRef.current = cluster;

    setTimeout(() => map.invalidateSize(), 100);
    return () => {
      map.remove();
      mapRef.current = null;
      clusterRef.current = null;
      markerMapRef.current.clear();
    };
  }, []);

  // Patch markers when filtered cases change. Defer to next animation frame
  // so the click that triggered this doesn't have to wait for clustering.
  useEffect(() => {
    const cluster = clusterRef.current;
    if (!cluster) return;

    const handle = requestAnimationFrame(() => {
      const next = new Set<string>();
      const toAdd: L.CircleMarker[] = [];
      const toRemove: L.CircleMarker[] = [];
      const existing = markerMapRef.current;

      // Pass 1: figure out additions
      for (const c of cases) {
        if (c.lat == null || c.lon == null) continue;
        next.add(c.id);
        if (existing.has(c.id)) continue;

        const pos = displayCoords.get(c.id) ?? [c.lat, c.lon];
        const color = CASE_TYPE_COLOR[c.caseType];
        const radius = 1.5 + Math.log10(Math.max(1, c.viewCount)) * 0.8;
        const m = L.circleMarker(pos, {
          radius,
          color,
          fillColor: color,
          fillOpacity: 0.6,
          weight: 1,
        });
        m.bindTooltip(
          () =>
            `<div style="font-size:11px;color:#a3e635;text-transform:uppercase;letter-spacing:.05em;">
                ${CASE_TYPE_LABEL[c.caseType]} · ${STATUS_LABEL[c.status]}
              </div>
              <div style="font-size:12px;font-weight:700;color:#f3f4f6;">${escapeHtml(c.caseName)}</div>
              <div style="font-size:11px;color:#9ca3af;">${escapeHtml(c.country ?? "?")} · ${c.crimeYear ?? "?"}</div>`,
          { direction: "top", offset: [0, -2], opacity: 0.95, sticky: true },
        );
        m.on("click", () => focusRef.current(c.id));
        existing.set(c.id, m);
        toAdd.push(m);
      }

      // Pass 2: figure out removals
      for (const [id, m] of existing) {
        if (next.has(id)) continue;
        toRemove.push(m);
        existing.delete(id);
      }

      // Bulk apply both deltas — markercluster batches these properly.
      if (toRemove.length > 0) cluster.removeLayers(toRemove);
      if (toAdd.length > 0) cluster.addLayers(toAdd);
    });

    return () => cancelAnimationFrame(handle);
  }, [cases]);

  // Fly to the selected country's *geographic* centre (or back to the world)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!country) {
      map.flyTo([20, 0], 2, { duration: 0.6 });
      return;
    }
    const geo = COUNTRY_GEO[country];
    if (geo) {
      map.flyTo([geo.lat, geo.lon], geo.zoom, { duration: 0.8 });
    }
  }, [country]);

  const resetView = () => {
    mapRef.current?.flyTo([20, 0], 2, { duration: 0.6 });
  };

  return (
    <div className="relative">
      <div ref={containerRef} className="h-[480px]" />
      <button
        type="button"
        onClick={resetView}
        title="返回世界視野（保留篩選）"
        className="absolute right-3 top-3 z-[500] flex h-9 w-9 items-center justify-center rounded-md border border-ink-700 bg-ink-900/90 text-gray-300 shadow-lg backdrop-blur transition hover:border-accent-neon hover:text-accent-neon"
      >
        <Globe2 className="h-4 w-4" />
      </button>
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (m) =>
    m === "&"
      ? "&amp;"
      : m === "<"
        ? "&lt;"
        : m === ">"
          ? "&gt;"
          : m === '"'
            ? "&quot;"
            : "&#39;",
  );
}
