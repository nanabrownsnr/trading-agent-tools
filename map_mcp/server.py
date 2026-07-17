from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from layers.points import PointsLayer
from layers.choropleth import ChoroplethLayer
from pydantic import BaseModel
from pathlib import Path
from typing import Any, Optional
import requests

class layer(BaseModel):
    name: str
    data: dict | list[dict]


class MapRequest(BaseModel):
    layers: list[layer]
    center: list[float] | None = None # only set this for a deliberate fixed view — otherwise the map auto-fits to rendered data
    zoom: int | None = None

points_layer = PointsLayer()
choropleth_layer = ChoroplethLayer()


LAYERS = {
    "points": points_layer,
    "choropleth" : choropleth_layer
}


mcp = FastMCP("map_mcp")

VIEW_URI = "ui://maps_mcp/map.html"
VIEW_HTML = (Path(__file__).parent / "views" / "dist" / "index.html").read_text(encoding="utf-8")


@mcp.resource(
    VIEW_URI,
    app=AppConfig(csp=ResourceCSP(resource_domains=["https://*.tile.openstreetmap.org"],
)))
def map_view():
    return VIEW_HTML


def _photon_geocode(location: str):
    
    feature = None
    
    headers = {
        "User-Agent": "maps-mcp/1.0 (twynity)"
    }
    url = f"https://photon.komoot.io/api/?q={location}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if not features:
            return feature
        feature = features[0]
    except Exception as e:
        return feature

    return feature

def _get_geoboundaries_geojson(iso: str, adm: str = "ADM0", name_filter: Optional[str] = None): 
    iso = iso.upper()
    adm = adm.upper()

    meta_url = f"https://www.geoboundaries.org/gbRequest.html?ISO={iso}&ADM={adm}"

    try:
        meta_resp = requests.get(meta_url, timeout=15)
        meta_resp.raise_for_status()
    except requests.RequestException as e:
        print(f"GeoBoundaries metadata request error: {e}")
        return False, None

    try:
        meta_data = meta_resp.json()
    except ValueError as e:
        print(f"GeoBoundaries metadata JSON parse error: {e}")
        return False, None

    # Metadata may be a list or a single object
    if isinstance(meta_data, list):
        if not meta_data:
            print("GeoBoundaries: no metadata entries found.")
            return False, None
        meta_entry = meta_data[0]
    else:
        meta_entry = meta_data

    gj_url = meta_entry.get("gjDownloadURL")
    if not gj_url:
        print("GeoBoundaries: gjDownloadURL not found in metadata.")
        return False, None

    try:
        gj_resp = requests.get(gj_url, timeout=30)
        gj_resp.raise_for_status()
    except requests.RequestException as e:
        print(f"GeoBoundaries GeoJSON download error: {e}")
        return False, None

    try:
        geojson = gj_resp.json()
    except ValueError as e:
        print(f"GeoBoundaries GeoJSON parse error: {e}")
        return False, None

    if name_filter:
        name_filter_lower = name_filter.lower()
        features: List[Dict[str, Any]] = geojson.get("features", [])
        filtered = [
            f for f in features
            if str(f.get("properties", {}).get("shapeName", "")).lower()
               == name_filter_lower
        ]

        if not filtered:
            print(f"No features found matching name '{name_filter}' in {iso} {adm}.")
            return False, None

        return True, {
            "type": "FeatureCollection",
            "features": filtered,
        }

    return True, geojson

def _downsample_polygon(feature: dict[str, Any], max_points: int = 7) -> dict[str, Any]:
    """
    Take a GeoJSON Feature with Polygon or MultiPolygon geometry
    and return a new Feature with a heavily downsampled polygon
    (max_points vertices per outer ring).

    This is a simple sampling approach, not a true geometric simplification.
    """
    geom = feature.get("geometry", {})
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])

    def sample_ring(ring: List[List[float]], n: int) -> List[List[float]]:
        """Sample at most n points from a ring, keeping first and last."""
        if len(ring) <= n:
            return ring

        # Ensure ring is closed (first == last)
        closed = (ring[0] == ring[-1])
        core = ring[:-1] if closed else ring

        step = max(1, len(core) // (n - 1))  # -1 because we'll add last separately
        sampled = core[0:len(core):step]

        # Guarantee we have at most n-1 core points
        sampled = sampled[: n - 1]

        # Add last point (close ring)
        last = ring[-1] if closed else core[-1]
        sampled.append(last)

        return sampled

    if gtype == "Polygon":
        # coords: [ [ [lon, lat], ... ] ]
        new_rings = []
        for i, ring in enumerate(coords):
            # Only downsample outer ring (i == 0); keep holes as-is or also downsample if you want
            if i == 0:
                new_rings.append(sample_ring(ring, max_points))
            else:
                new_rings.append(ring)
        new_geom = {"type": "Polygon", "coordinates": new_rings}

    elif gtype == "MultiPolygon":
        # coords: [ [ [ [lon, lat], ... ] ], ... ]
        new_polys = []
        for poly in coords:
            new_rings = []
            for i, ring in enumerate(poly):
                if i == 0:
                    new_rings.append(sample_ring(ring, max_points))
                else:
                    new_rings.append(ring)
            new_polys.append(new_rings)
        new_geom = {"type": "MultiPolygon", "coordinates": new_polys}

    else:
        # Not a polygon geometry; return as-is
        return feature

    return {
        "type": "Feature",
        "geometry": new_geom,
        "properties": feature.get("properties", {}),
    }


@mcp.tool()
def get_location_coordinates(location: str):
    coordinates = None
    feature = _photon_geocode(location)

    if feature is None:
        return coordinates
    
    geometry = feature.get("geometry", {})
    properties = feature.get("properties", {})   
    coords = geometry.get("coordinates")
    lon, lat = coords[0], coords[1]
    
    coordinates = {
        "lat": lat,
        "lon": lon,
        "name": properties.get("name"),
        "country": properties.get("country"),
        "countrycode": properties.get("countrycode")
    }
    
    return coordinates



    if response.status_code == 200:
        try:
            results = response.json()
            features = results.get("features", [])
            if not features:
                return data

            feature = features[0]
            geometry = feature.get("geometry", {})
            properties = feature.get("properties", {})   
            coords = geometry.get("coordinates")
            lon, lat = coords[0], coords[1]
            
            data = {
                "lat": lat,
                "lon": lon,
                "name": properties.get("name"),
                "country": properties.get("country"),
                "countrycode": properties.get("countrycode")
            }


        except ValueError:
            return data

@mcp.tool()
def get_location_polygon_geojson(location: str):
    """
    Given a free-text location (e.g. 'Ghana', 'Ashanti Region', 'Los Angeles'),
    query Nominatim and return the best match as a GeoJSON Feature
    with polygon/multipolygon geometry when available.

    Returns:
        (success, feature_geojson or None)

        feature_geojson example:
        {
            "type": "Feature",
            "geometry": { ... polygon or multipolygon ... },
            "properties": { ... Nominatim fields ... }
        }
    """
    # Nominatim search endpoint with polygon_geojson=1 to get boundaries
    base_url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": location,
        "format": "jsonv2",
        "polygon_geojson": 1,
        "addressdetails": 1,
        "limit": 1,  # best match only
    }
    headers = {
        "User-Agent": "maps-mcp/1.0 (twynity)"  # Nominatim requires a UA
    }

    try:
        resp = requests.get(base_url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Nominatim request error: {e}")
        return False, None

    try:
        results = resp.json()
    except ValueError as e:
        print(f"Nominatim JSON parse error: {e}")
        return False, None

    if not results:
        print(f"No Nominatim results for location: {location}")
        return False, None

    best = results[0]

    # Nominatim returns 'geojson' field when polygon_geojson=1
    geometry = best.get("geojson")
    if not geometry:
        print(f"No polygon GeoJSON available for location: {location}")
        return False, None

    # Build a proper GeoJSON Feature
    feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "display_name": best.get("display_name"),
            "osm_id": best.get("osm_id"),
            "osm_type": best.get("osm_type"),
            "class": best.get("class"),
            "type": best.get("type"),
            "importance": best.get("importance"),
            "boundingbox": best.get("boundingbox"),
            "address": best.get("address"),
        },
    }

    simplified_feature = _downsample_polygon(feature)


    return True, simplified_feature

@mcp.tool()
def get_map_layers():
    """
    Returns all supported map layers and their schemas.
    """

    return {
        "layers": [
            layer.metadata
            for layer in LAYERS.values()
        ]
    }


def _summarize(processed_layers: list[dict]) -> str:
    """Build a compact text summary of what was rendered, for the model."""
    parts = []
    for layer in processed_layers:
        if layer["type"] == "points":
            labels = [p["label"] for p in layer["points"] if p.get("label")]
            preview = ", ".join(labels[:5])
            more = f" and {len(labels) - 5} more" if len(labels) > 5 else ""
            parts.append(f"{len(layer['points'])} point(s) ({preview}{more})")

    return f"Rendered a map with: {'; '.join(parts)}."

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def render_map(request: MapRequest) -> ToolResult:
    """
    Renders the map based on the required layer data, ensure you follow the example of the layer you are rendering and dont miss any required parameters.
    """
    processed_layers = []
     
    try:
        processed_layers = []
        for layer in request.layers:
            processor = LAYERS.get(layer.name)
            if processor is None:
                return ToolResult(content=f"Unknown layer type: {layer.name}")
            processed_layers.append(processor.process(layer.data))
    except ValueError as e:
        return ToolResult(content=str(e))
    
    structured = {
        "center": request.center,
        "zoom": request.zoom,
        "layers": processed_layers,
    }

    content = _summarize(processed_layers)
 
    return ToolResult(
        content=content,
        structured_content=structured,
        meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI}
    )


middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["mcp-protocol-version", "mcp-session-id", "Authorization", "Content-Type"],
        expose_headers=["mcp-session-id"],
    )
]
app = mcp.http_app(middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)