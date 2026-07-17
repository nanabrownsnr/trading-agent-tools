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

function renderChoropleth(layer) {
    const values = layer.geojson.features
        .map((f) => f.properties?.[layer.value_field])
        .filter((v) => v != null && !Number.isNaN(v));

    const min = Math.min(...values);
    const max = Math.max(...values);

    const geoLayer = L.geoJSON(layer.geojson, {
        style: (feature) => ({
            fillColor: feature.properties?.colour || colorForValue(feature.properties?.[layer.value_field], min, max),
            fillOpacity: 0.75,
            weight: 1,
            color: "#333333",
        }),
        onEachFeature: (feature, lyr) => {
            const name = feature.properties?.name || feature.properties?.region || "Region";
            const value = feature.properties?.[layer.value_field];
            lyr.bindPopup(`<strong>${name}</strong><br>${layer.value_field}: ${value ?? "n/a"}`);
        },
    }).addTo(map);

    activeLayers.push(geoLayer);
    return geoLayer;
}


const LAYER_RENDERERS = {
    points: renderPoints,
    choropleth: renderChoropleth,
};

app.ontoolresult = (result) => {
    const data = result.structuredContent;
    if (!data) return;

    clearLayers();

    if (data.center) {
        map.setView(data.center, data.zoom ?? map.getZoom());
    } else if (activeLayers.length > 0) {
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