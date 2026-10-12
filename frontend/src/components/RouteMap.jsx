import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { RISK_COLORS, ROUTE_COLORS } from "../api";

import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
const DefaultIcon = L.icon({ iconUrl: markerIcon, shadowUrl: markerShadow, iconSize: [25, 41], iconAnchor: [12, 41] });
L.Marker.prototype.options.icon = DefaultIcon;

const TILES = {
  dark: { url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", attr: "&copy; OpenStreetMap &copy; CARTO" },
  light: { url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", attr: "&copy; OpenStreetMap contributors" },
  terrain: { url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", attr: "&copy; OpenStreetMap contributors, SRTM | style: &copy; OpenTopoMap (CC-BY-SA)" },
  satellite: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr: "Imagery &copy; Esri & contributors" },
};

function hav(a, b) {
  const R = 3958.8, dLa = (b[0] - a[0]) * Math.PI / 180, dLn = (b[1] - a[1]) * Math.PI / 180;
  const h = Math.sin(dLa / 2) ** 2 + Math.cos(a[0] * Math.PI / 180) * Math.cos(b[0] * Math.PI / 180) * Math.sin(dLn / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function pointAtMile(path, mile) {
  let acc = 0;
  for (let i = 1; i < path.length; i++) {
    const seg = hav(path[i - 1], path[i]);
    if (acc + seg >= mile) {
      const f = seg === 0 ? 0 : (mile - acc) / seg;
      return [path[i - 1][0] + f * (path[i][0] - path[i - 1][0]),
              path[i - 1][1] + f * (path[i][1] - path[i - 1][1])];
    }
    acc += seg;
  }
  return path[path.length - 1];
}

export default function RouteMap({ plan, corridor, selectedRoute, recommendedIndex, heatHour, showHeat, dark, truckMile, mapStyle }) {
  const divRef = useRef(null);
  const mapRef = useRef(null);
  const tileRef = useRef(null);
  const layerRef = useRef(null);
  const heatRef = useRef(null);
  const truckRef = useRef(null);

  useEffect(() => {
    if (mapRef.current) return;
    const map = L.map(divRef.current).setView([39.5, -98.35], 4);
    mapRef.current = map;
  }, []);

  // theme tiles (+ terrain / satellite styles)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tileRef.current) tileRef.current.remove();
    const key = mapStyle === "terrain" || mapStyle === "satellite" ? mapStyle : (dark ? "dark" : "light");
    const t = TILES[key];
    tileRef.current = L.tileLayer(t.url, { attribution: t.attr, maxZoom: 18 }).addTo(map);
  }, [dark, mapStyle]);

  // routes + checkpoints
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !plan) return;
    if (layerRef.current) layerRef.current.remove();
    const g = L.layerGroup();

    plan.routes.forEach((route, ri) => {
      const isSel = ri === selectedRoute;
      const isRec = ri === (recommendedIndex ?? 0);
      L.polyline(route.path, {
        color: ROUTE_COLORS[ri % ROUTE_COLORS.length],
        weight: isSel ? 6 : 3, opacity: isSel ? 1 : 0.5,
        dashArray: isRec ? null : "8 6",
      }).bindTooltip(`Route ${ri + 1}${isRec ? " — RECOMMENDED" : ""}`, { sticky: true }).addTo(g);

      // animated "flow" overlay on the selected route — reads as drawing/motion
      if (isSel) {
        L.polyline(route.path, {
          color: "#ffffff", weight: 2.5, opacity: 0.85,
          className: "route-flow", interactive: false,
        }).addTo(g);
      }

      if (isSel) {
        route.checkpoints.forEach((cp) => {
          L.circleMarker([cp.lat, cp.lng], {
            radius: 7, color: dark ? "#fff" : "#111", weight: 1,
            fillColor: RISK_COLORS[cp.level], fillOpacity: 0.95,
          }).bindPopup(
            `<b>Mile ${cp.mile}</b> — <b style="color:${RISK_COLORS[cp.level]}">${cp.level}</b><br/>` +
            `ETA: ${new Date(cp.eta).toUTCString().slice(0, 22)} UTC<br/>` +
            `Wind: ${cp.wind_mph} mph · Rain: ${cp.rain_inhr} in/hr · Snow: ${cp.snow_inhr} in/hr<br/>` +
            `<i>${cp.reasons.join("; ")}</i>`
          ).addTo(g);
        });
      }
    });

    L.marker([plan.origin.lat, plan.origin.lng]).bindTooltip("Origin").addTo(g);
    L.marker([plan.destination.lat, plan.destination.lng]).bindTooltip("Destination").addTo(g);

    g.addTo(map);
    layerRef.current = g;
    map.fitBounds(L.latLngBounds(plan.routes[selectedRoute].path).pad(0.15));
  }, [plan, selectedRoute, dark]);

  // heatmap — risk circles colored by level at the selected forecast hour
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (heatRef.current) { heatRef.current.remove(); heatRef.current = null; }
    if (!showHeat || !corridor) return;
    const g = L.layerGroup();
    const names = Object.keys(RISK_COLORS);
    corridor.points.forEach((p) => {
      const score = p.hours[heatHour];
      const level = names[score];
      L.circle([p.lat, p.lng], {
        radius: 22000, color: RISK_COLORS[level], weight: 0,
        fillColor: RISK_COLORS[level], fillOpacity: 0.35,
        className: "heat-pulse", interactive: false,
      }).bindTooltip(`${level} — mile ${p.mile}`, { sticky: true }).addTo(g);
    });
    g.addTo(map);
    heatRef.current = g;
  }, [corridor, heatHour, showHeat]);

  // animated truck
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !plan) return;
    if (truckRef.current) { truckRef.current.remove(); truckRef.current = null; }
    if (truckMile === null || truckMile === undefined) return;
    const pos = pointAtMile(plan.routes[selectedRoute].path, truckMile);
    const icon = L.divIcon({ html: "<div style='font-size:30px;filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))'>🚚</div>", className: "", iconSize: [30, 30], iconAnchor: [15, 15] });
    truckRef.current = L.marker(pos, { icon, zIndexOffset: 1000 }).addTo(map);
  }, [plan, selectedRoute, truckMile]);

  return <div ref={divRef} className="leaflet-holder" />;
}
