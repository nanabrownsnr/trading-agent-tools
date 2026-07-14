from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from layers.points import PointsLayer
from layers.choropleth import ChoroplethLayer
from pydantic import BaseModel
from pathlib import Path


class layer(BaseModel):
    name: str
    data: list[dict]


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
VIEW_HTML = (Path(__file__).parent / "views" / "dist" / "index.html").read_text()


@mcp.resource(
    VIEW_URI,
    app=AppConfig(csp=ResourceCSP(resource_domains=["https://*.tile.openstreetmap.org"],
)))
def map_view():
    return VIEW_HTML



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