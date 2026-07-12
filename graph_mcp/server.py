from pathlib import Path
from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from charts import build_line_chart
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

mcp = FastMCP("graph-mcp")

VIEW_URI = "ui://graph_mcp/line-chart.html"
VIEW_HTML = (Path(__file__).parent / "views" / "line_chart.html").read_text()


@mcp.resource(
    VIEW_URI,
    app=AppConfig(csp=ResourceCSP(
        resource_domains=["https://unpkg.com", "https://cdn.plot.ly"],
    ))
)

def line_chart_view() -> str:
    return VIEW_HTML

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def generate_line_chart(data: list[dict], x_field: str, y_field: str,
                         series_field: str | None = None, title: str = "") -> ToolResult:
    """
    Render an interactive price/time-series line chart (zoom, pan, hover).
    data: rows from any db-mcp, e.g. get_price output.
    """
    try:
        figure = build_line_chart(data, x_field, y_field, series_field, title)
    except ValueError as e:
        return ToolResult(content =str(e))

    values = [row[y_field] for row in data if y_field in row]

    return ToolResult(
        content=values, 
        structured_content={"figure": figure},
        meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI}
    )




middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"], 
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "mcp-protocol-version",
            "mcp-session-id",
            "Authorization",
            "Content-Type",
        ],
        expose_headers=["mcp-session-id"],
    )
]
app = mcp.http_app(
    middleware=middleware
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(transport="streamable-http", host="0.0.0.0", port=8002)

