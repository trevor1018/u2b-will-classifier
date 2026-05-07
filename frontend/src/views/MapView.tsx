import { useEffect, useRef } from "react";
import L from "leaflet";
import { useStore, useFilteredCases } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, STATUS_LABEL } from "../lib/types";

// One imperative Leaflet map handles 400+ markers far cheaper than 400+
// React `<CircleMarker>` instances — and avoids the per-marker prop-churn
// re-render loop that crashed earlier.
export function MapView() {
  const cases = useFilteredCases();
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
      center: [20, 30],
      zoom: 2,
      worldCopyJump: true,
      preferCanvas: true, // canvas renderer — much faster for many markers
      zoomControl: true,
    });
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      },
    ).addTo(map);
    const layer = L.layerGroup().addTo(map);
    mapRef.current = map;
    markerLayerRef.current = layer;
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
      const radius = 6 + Math.log10(Math.max(1, c.viewCount)) * 1.6;
      const marker = L.circleMarker([c.lat, c.lon], {
        radius,
        color,
        fillColor: color,
        fillOpacity: 0.55,
        weight: 1.5,
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
