import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet.markercluster";
import { Globe2 } from "lucide-react";
import { useStore, useFilteredCases } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, STATUS_LABEL } from "../lib/types";
import { COUNTRY_GEO } from "../lib/countryGeo";

// One imperative Leaflet map handles 400+ markers far cheaper than 400+
// React `<CircleMarker>` instances. We further use leaflet.markercluster
// so dense regions (日本 has 115 cases) collapse into count badges instead
// of overlapping dots — and crucially its `addLayers([])` is a real bulk
// API, far faster than calling `marker.addTo(layer)` 405 times.
//
// Behaviour:
//  - Initial view = entire world, single copy. minZoom + maxBounds prevent
//    zooming out to where the world repeats.
//  - Selecting a country flies to its *geographic* centre (static dict).
//  - Click marker → opens the right-hand CaseDetailDrawer (with YT embed).
//  - Hover any marker for a quick dark tooltip.
//  - Top-right Globe button resets the view without clearing filters.
export function MapView() {
  const cases = useFilteredCases();
  const country = useStore((s) => s.country);
  const focus = useStore((s) => s.focusCase);
  const focusRef = useRef(focus);
  focusRef.current = focus;

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  // markerClusterGroup is typed as L.MarkerClusterGroup but the plugin
  // augments L globally and TS doesn't see the type without extra config.
  // Refining via `any` here keeps the rest of the file strict-typed.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const clusterRef = useRef<any>(null);

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
      // Keep clusters tight enough that you can still see individual markers
      // at country-level zooms.
      maxClusterRadius: 40,
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      chunkedLoading: true, // lets the lib break the add operation across frames
      iconCreateFunction: (cluster: { getChildCount: () => number }) => {
        const n = cluster.getChildCount();
        // size scales with count
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
    };
  }, []);

  // Repaint markers whenever filtered cases change
  useEffect(() => {
    const cluster = clusterRef.current;
    if (!cluster) return;

    // Build all markers up-front so we can use the bulk-add API.
    const markers: L.CircleMarker[] = [];
    for (const c of cases) {
      if (c.lat == null || c.lon == null) continue;
      const color = CASE_TYPE_COLOR[c.caseType];
      const radius = 1.5 + Math.log10(Math.max(1, c.viewCount)) * 0.8;
      const m = L.circleMarker([c.lat, c.lon], {
        radius,
        color,
        fillColor: color,
        fillOpacity: 0.6,
        weight: 1,
      });
      // Lazy tooltip: HTML only built on hover, not for every marker on add.
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
      markers.push(m);
    }

    // Bulk replace — this is the entire reason we use markerClusterGroup
    // over a plain L.layerGroup. addLayers/removeLayers are batched and
    // chunked across animation frames internally.
    cluster.clearLayers();
    cluster.addLayers(markers);
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
