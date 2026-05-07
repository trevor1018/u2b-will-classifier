import { useEffect, useRef } from "react";
import L from "leaflet";
import { useStore, useFilteredCases } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, STATUS_LABEL } from "../lib/types";

// One imperative Leaflet map handles 400+ markers far cheaper than 400+
// React `<CircleMarker>` instances — and avoids the per-marker prop-churn
// re-render loop that crashed earlier.
//
// Behaviour:
//  - Initial view = entire world, single copy
//  - minZoom + maxBounds prevent zooming out far enough to see world repeat
//  - Selecting a country (from FilterBar) flies the map to that country's
//    case-bounding-box; deselecting flies back to the world view.
export function MapView() {
  const cases = useFilteredCases();
  const country = useStore((s) => s.country);
  const focus = useStore((s) => s.focusCase);
  const focusRef = useRef(focus);
  focusRef.current = focus;

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerLayerRef = useRef<L.LayerGroup | null>(null);

  // Init once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [20, 0],
      zoom: 2,
      minZoom: 2,
      worldCopyJump: false,
      maxBounds: L.latLngBounds([-85, -180], [85, 180]),
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
        noWrap: true, // don't repeat tiles past the antimeridian
        bounds: L.latLngBounds([-85, -180], [85, 180]),
      },
    ).addTo(map);
    const layer = L.layerGroup().addTo(map);
    mapRef.current = map;
    markerLayerRef.current = layer;
    // Force a quick re-fit on next tick so the map sizes itself correctly
    // even when the panel was hidden during initial mount.
    setTimeout(() => map.invalidateSize(), 100);
    return () => {
      map.remove();
      mapRef.current = null;
      markerLayerRef.current = null;
    };
  }, []);

  // Repaint markers whenever filtered cases change
  useEffect(() => {
    const layer = markerLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    cases.forEach((c) => {
      if (c.lat == null || c.lon == null) return;
      const color = CASE_TYPE_COLOR[c.caseType];
      // Half the previous radius — easier to see clusters of markers in
      // dense regions like Japan / USA.
      const radius = 1.5 + Math.log10(Math.max(1, c.viewCount)) * 0.8;
      const marker = L.circleMarker([c.lat, c.lon], {
        radius,
        color,
        fillColor: color,
        fillOpacity: 0.6,
        weight: 1,
      }).bindPopup(
        `<div style="font-size:11px;letter-spacing:.05em;color:#a3e635;text-transform:uppercase;">
            ${CASE_TYPE_LABEL[c.caseType]} · ${STATUS_LABEL[c.status]}
          </div>
          <div style="font-size:13px;font-weight:700;margin-top:4px;">${escapeHtml(c.caseName)}</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:2px;">
            ${escapeHtml(c.country ?? "?")} · ${escapeHtml(c.city ?? "?")} · ${c.crimeYear ?? "?"}
          </div>
          <div style="font-size:11px;color:#6b7280;margin-top:2px;">
            ${c.viewCount.toLocaleString()} 觀看
          </div>`,
      );
      marker.on("click", () => focusRef.current(c.id));
      marker.addTo(layer);
    });
  }, [cases]);

  // Fly to the selected country (or back to the world)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!country) {
      // Reset to world view
      map.flyTo([20, 0], 2, { duration: 0.6 });
      return;
    }

    // Build a bounding box from all cases of the selected country with coords
    const points: L.LatLng[] = [];
    cases.forEach((c) => {
      if (c.country === country && c.lat != null && c.lon != null) {
        points.push(L.latLng(c.lat, c.lon));
      }
    });

    if (points.length === 0) {
      // No coords → don't move (e.g. "不明")
      return;
    }
    const bounds = L.latLngBounds(points);
    // Pad so markers aren't right at the edge
    map.flyToBounds(bounds.pad(0.3), {
      duration: 0.8,
      maxZoom: 6, // don't zoom in too aggressively for tiny single-city sets
    });
  }, [country, cases]);

  return <div ref={containerRef} className="h-[480px]" />;
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
