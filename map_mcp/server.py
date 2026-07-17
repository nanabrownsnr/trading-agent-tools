from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Any, Optional
import requests

class point_properties(BaseModel):
    latitude: float
    longitude: float
    label: str
    value: str | None = None

class Points(BaseModel):
    points: list[point_properties]


class feature_properties(BaseModel):
    name: str
    value_label: str
    value_quantity: float
    colour: str

class feature_geometry(BaseModel):
    type: str
    coordinates: list[list]

class Feature(BaseModel):
    properties: feature_properties
    geometry: feature_geometry
    type: str

class Choropleth(BaseModel):
    feature: list[Feature]
    value_field: str

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
        features: list[Dict[str, Any]] = geojson.get("features", [])
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

def _downsample_polygon(feature: dict[str, Any], min_points: int = 4, max_points: int = 7) -> dict[str, Any]:
    """
    Take a GeoJSON Feature with Polygon or MultiPolygon geometry
    and return a new Feature with a heavily downsampled polygon
    (max_points vertices per outer ring).

    This is a simple sampling approach, not a true geometric simplification.
    """
    if max_points < min_points:
        max_points = min_points

    geom = feature.get("geometry", {})
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])

    def sample_ring(ring: list[list[float]], n: int) -> list[list[float]]:
        """Sample at most n points from a ring, keeping first and last."""
        # If ring is already short, just return it
        if len(ring) <= n:
            return ring

        # Ensure ring is closed (first == last)
        closed = (ring[0] == ring[-1])
        core = ring[:-1] if closed else ring

        # We want total points including last to be <= n
        # So we sample at most (n - 1) from core, then add last.
        target_core_points = max(1, n - 1)

        step = max(1, len(core) // target_core_points)
        sampled = core[0:len(core):step]

        # Guarantee we have at most n-1 core points
        sampled = sampled[:target_core_points]

        # Add last point (close ring)
        last = ring[-1] if closed else core[-1]
        sampled.append(last)

        return sampled

    if gtype == "Polygon":
        # coords: [ [ [lon, lat], ... ] ]
        new_rings = []
        for i, ring in enumerate(coords):
            # Only downsample outer ring (i == 0); keep holes as-is
            if i == 0:
                new_rings.append(sample_ring(ring, target_points))
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
                    new_rings.append(sample_ring(ring, target_points))
                else:
                    new_rings.append(ring)
            new_polys.append(new_rings)
        new_geom = {"type": "MultiPolygon", "coordinates": new_polys}

    else:
        return feature

    return {
        "type": "Feature",
        "geometry": new_geom,
        "properties": feature.get("properties", {}),
    }


@mcp.tool()
def get_location_coordinates(location: str):
    
    """
    Look up the approximate coordinates for a named location.

    Use this when:
    - You need a single point (latitude/longitude) for a place.
    - You want to center a map or place a marker for a city, region, or country.
    - You are not concerned with exact administrative boundaries, only a representative point.

    Args:
        location: A free-text place name, e.g. "Accra", "Ghana", "Los Angeles, USA".

    Returns:
        A dict with:
            {
                "lat": float,        # latitude
                "lon": float,        # longitude
                "name": str | None,  # resolved name
                "country": str | None,
                "countrycode": str | None
            }
        or None if the location cannot be resolved.
    """
    
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
    Look up a simplified polygon or multipolygon boundary for a named location.

    Use this when:
    - You need the approximate shape of a country, region, or city.
    - You want to draw a boundary on the map (e.g. for a choropleth).
    - You need more than just a point; you need an area outline.

    This tool queries Nominatim with polygon_geojson=1 and then heavily
    downsamples the outer ring so the geometry is small enough for use
    in prompts and lightweight visualizations.

    Args:
        location: A free-text place name, e.g. "Ghana",
                  "Ashanti Region, Ghana", "Los Angeles, California".

    Returns:
        A tuple (success, feature) where:
            success: bool - True if a polygon was found.
            feature: dict | None - A GeoJSON Feature:
                {
                    "type": "Feature",
                    "geometry": { "type": "Polygon" | "MultiPolygon", "coordinates": [...] },
                    "properties": {
                        "display_name": str,
                        "osm_id": int,
                        "osm_type": str,
                        "class": str | None,
                        "type": str | None,
                        "importance": float | None,
                        "boundingbox": [str, str, str, str] | None,
                        "address": dict | None
                    }
                }
        If no polygon is available, returns (False, None).
    """

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

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def render_choropleth_map(layers: list[Choropleth], center: list[float] , zoom: int) -> ToolResult:
    """
    Render a choropleth map layer from polygon features with numeric values.

    Use this when:
    - You have one or more polygon Features (e.g. regions, countries, districts)
      and a numeric field you want to visualize as a color scale.
    - You want to show regional differences (e.g. production, risk, demand)
      across areas on the map.

    Args:
        feature:
            A list of Feature objects, each representing a polygon or multipolygon.
            Each Feature.properties should include at least:
                - name: str
                - value_label: str        # human-readable label for the value
                - value_quantity: float   # numeric value to visualize
                - colour: str             # explicit color hex
        value_field:
            The name of the numeric property to use for coloring, typically "value_quantity".
        center:
            [lat, lon] to center the map view.
        zoom:
            Initial zoom level for the map.

    Behavior:
        - Wraps the features into a GeoJSON FeatureCollection.
        - Sends a single "choropleth" layer to the map UI with:
            {
              "type": "choropleth",
              "geojson": { "type": "FeatureCollection", "features": [...] },
              "value_field": value_field
            }

    Returns:
        ToolResult with:
            - content: a brief text summary of what was rendered.
            - structured_content: {
                  "center": [lat, lon],
                  "zoom": zoom,
                  "layers": [ { type: "choropleth", ... } ]
              }
            - meta: UI resource URI for the map.
    """
    processed_layers = []
    for l in layers:
        feature_dicts = [f.model_dump() for f in l.feature]
        geojson = {
            "type": "FeatureCollection",
            "features": feature_dicts,
        }
        processed_layers.append({
            "type": "choropleth",
            "geojson": geojson,
            "value_field": l.value_field,
        })

    
    structured = {
        "center": center,
        "zoom": zoom,
        "layers": processed_layers,
    }

    content = f"Rendered {len(processed_layers)} choropleth layer(s) on the canvas."
 
    return ToolResult(
        content=content,
        structured_content=structured,
        meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI}
    )

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def render_points_map(layers: list[Points], center: list[float] , zoom: int) -> ToolResult:
    """
    Render a map with one or more point markers.

    Use this when:
    - You want to show specific locations as markers (cities, ports, facilities, etc.).
    - You have a list of coordinates with labels and optional values.
    - You want a simple point-based visualization (no polygons).

    Args:
        points:
            A list of Point objects, each with:
                - latitude: float
                - longitude: float
                - label: str
                - value: str | None   # optional extra info shown in the popup
        center:
            [lat, lon] to center the map view.
        zoom:
            Initial zoom level for the map.

    Behavior:
        - Converts the list of Point objects into a single "points" layer:
            {
              "type": "points",
              "points": [
                { "latitude": ..., "longitude": ..., "label": "...", "value": "..." },
                ...
              ]
            }
        - Sends this layer to the map UI for rendering.

    Returns:
        ToolResult with:
            - content: a brief text summary of what was rendered.
            - structured_content: {
                  "center": [lat, lon],
                  "zoom": zoom,
                  "layers": [ { type: "points", points: [...] } ]
              }
            - meta: UI resource URI for the map.
    """
    processed_layers = []
    for l in layers:
        point_dicts = [p.model_dump() for p in l.points]
        processed_layers.append({
            "type": "points",
            "points": point_dicts,
        })


    structured = {
        "center": center,
        "zoom": zoom,
        "layers": processed_layers ,
    }

    content = f"Rendered {len(processed_layers)} points layer(s) on the canvas."
 
    return ToolResult(
        content=content,
        structured_content=structured,
        meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI}
    )

#ToDo
#def render_composite_map()

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