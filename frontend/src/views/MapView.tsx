import { useEffect, useRef } from "react";
import L from "leaflet";
import { useStore, useFilteredCases } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, STATUS_LABEL } from "../lib/types";
import { COUNTRY_GEO } from "../lib/countryGeo";

// One imperative Leaflet map handles 400+ markers far cheaper than 400+
// React `<CircleMarker>` instances — and avoids the per-marker prop-churn
// re-render loop that crashed earlier.
//
// Behaviour:
//  - Initial view = entire world, single copy
//  - minZoom + maxBounds prevent zooming out far enough to see world repeat
//  - Selecting a country flies the map to that country's *geographic* centre
//    (from a static dict, not the case data points — cross-border cases &
//    sparse data made the bounds approach misleading)
//  - Click marker → opens the right-hand CaseDetailDrawer (with YT embed).
//    Hover for a quick tooltip; no Leaflet popup that could be clipped by
//    panel overflow on small viewports.
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
        noWrap: true,
        bounds: L.latLngBounds([-85, -180], [85, 180]),
      },
    ).addTo(map);
    const layer = L.layerGroup().addTo(map);
    mapRef.current = map;
    markerLayerRef.current = layer;
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
      const radius = 1.5 + Math.log10(Math.max(1, c.viewCount)) * 0.8;
      const marker = L.circleMarker([c.lat, c.lon], {
        radius,
        color,
        fillColor: color,
        fillOpacity: 0.6,
        weight: 1,
      }).bindTooltip(
        // Lightweight hover preview. Stays inside the map pane and doesn't
        // open on click (so no fight with the drawer).
        `<div style="font-size:11px;color:#a3e635;text-transform:uppercase;letter-spacing:.05em;">
            ${CASE_TYPE_LABEL[c.caseType]} · ${STATUS_LABEL[c.status]}
          </div>
          <div style="font-size:12px;font-weight:700;color:#f3f4f6;">${escapeHtml(c.caseName)}</div>
          <div style="font-size:11px;color:#9ca3af;">${escapeHtml(c.country ?? "?")} · ${c.crimeYear ?? "?"}</div>`,
        { direction: "top", offset: [0, -2], opacity: 0.95, sticky: true },
      );
      marker.on("click", () => focusRef.current(c.id));
      marker.addTo(layer);
    });
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
      return;
    }

    // Country not in our static dict (e.g. "不明") → don't move the map
  }, [country]);

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
