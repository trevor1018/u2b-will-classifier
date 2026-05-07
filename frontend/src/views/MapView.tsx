import { useMemo } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import { useStore, useFilteredCases } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, STATUS_LABEL } from "../lib/types";

export function MapView() {
  const cases = useFilteredCases();
  const focus = useStore((s) => s.focusCase);

  const points = useMemo(
    () => cases.filter((c) => c.lat != null && c.lon != null),
    [cases],
  );

  // Radius scales with view count (log so it doesn't explode)
  const radiusFor = (views: number) => 6 + Math.log10(Math.max(1, views)) * 1.6;

  return (
    <div className="h-[480px]">
      <MapContainer
        center={[20, 30]}
        zoom={2}
        worldCopyJump
        scrollWheelZoom
        className="h-full w-full"
      >
        {/* Carto dark-matter — free, fits the case-file aesthetic */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains={["a", "b", "c", "d"]}
          maxZoom={19}
        />
        {points.map((c) => (
          <CircleMarker
            key={c.id}
            center={[c.lat!, c.lon!]}
            radius={radiusFor(c.viewCount)}
            pathOptions={{
              color: CASE_TYPE_COLOR[c.caseType],
              fillColor: CASE_TYPE_COLOR[c.caseType],
              fillOpacity: 0.55,
              weight: 1.5,
            }}
            eventHandlers={{
              click: () => focus(c.id),
            }}
          >
            <Popup>
              <div className="space-y-1">
                <div className="text-[11px] uppercase tracking-wider text-accent-neon">
                  {CASE_TYPE_LABEL[c.caseType]} · {STATUS_LABEL[c.status]}
                </div>
                <div className="text-sm font-bold">{c.caseName}</div>
                <div className="text-xs text-gray-400">
                  {c.country} · {c.city} · {c.crimeYear ?? "?"}
                </div>
                <div className="text-xs text-gray-500">
                  {c.viewCount.toLocaleString()} 觀看
                </div>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
