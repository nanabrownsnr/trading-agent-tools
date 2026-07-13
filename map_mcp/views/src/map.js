import { App } from "@modelcontextprotocol/ext-apps";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: markerIcon2x,
    iconUrl: markerIcon,
    shadowUrl: markerShadow,
});


const app = new App({ name: "map_mcp", version: "1.0.0" });
const map = L.map("map").setView([0, 0], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 18,
}).addTo(map);

let activeLayers = [];

function clearLayers() {
    activeLayers.forEach((layer) => map.removeLayer(layer));
    activeLayers = [];
}

function renderPoints(layer) {
    const group = L.layerGroup();
    (layer.points || []).forEach((p) => {
        const marker = L.marker([p.lat, p.lng]);
        if (p.label || p.value != null) {
            marker.bindPopup(`${p.label || ""}${p.value != null ? `<br>value: ${p.value}` : ""}`);
        }
        marker.addTo(group);
    });
    group.addTo(map);
    activeLayers.push(group);
    return group;
}


const LAYER_RENDERERS = {
    points: renderPoints
};

app.ontoolresult = (result) => {
    const data = result.structuredContent;
    if (!data) return;

    clearLayers();

    if (data.center) {
        // Explicit center/zoom always wins, if the caller wants a fixed view.
        map.setView(data.center, data.zoom ?? map.getZoom());
    } else if (activeLayers.length > 0) {
        // Otherwise, auto-fit to whatever was actually rendered.
        try {
            const group = L.featureGroup(activeLayers.filter((l) => typeof l.getBounds === "function"));
            if (group.getLayers().length > 0) {
                map.fitBounds(group.getBounds(), { padding: [30, 30] });
            }
        } catch (e) {
            console.warn("Could not auto-fit bounds:", e);
        }
    }

    (data.layers || []).forEach((layer) => {
        const renderer = LAYER_RENDERERS[layer.type];
        if (renderer) {
            renderer(layer);
        } else {
            console.warn(`Unknown layer type: ${layer.type}`);
        }
    });
};
app.connect();