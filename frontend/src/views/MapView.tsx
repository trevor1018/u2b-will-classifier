import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet.markercluster";
import { Globe2 } from "lucide-react";
import { useStore, useFilteredCases } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, STATUS_LABEL } from "../lib/types";
import { COUNTRY_GEO } from "../lib/countryGeo";

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
  const country = useStore((s) => s.country);
  const focus = useStore((s) => s.focusCase);
  const focusRef = useRef(focus);
  focusRef.current = focus;

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
      spiderfyOnMaxZoom: true,
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

        const color = CASE_TYPE_COLOR[c.caseType];
        const radius = 1.5 + Math.log10(Math.max(1, c.viewCount)) * 0.8;
        const m = L.circleMarker([c.lat, c.lon], {
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
