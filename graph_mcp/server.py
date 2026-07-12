from pathlib import Path
from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from charts import build_line_chart, build_candlestick_chart
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

mcp = FastMCP("graph-mcp")

VIEW_URI_LINE = "ui://graph_mcp/line-chart.html"
VIEW_HTML_LINE = (Path(__file__).parent / "views" / "dist" / "index.html").read_text()

@mcp.resource(
    VIEW_URI_LINE,
    app=AppConfig(csp=ResourceCSP(
        resource_domains=["https://cdn.plot.ly"],
    ))
)
def line_chart_view() -> str:
    return VIEW_HTML_LINE


@mcp.tool(app=AppConfig(resource_uri=VIEW_URI_LINE))
def generate_line_chart(data: list[dict], x_field: str, y_field: str,
                         series_field: str | None = None, title: str = "") -> ToolResult:
    """
    Render an interactive price/time-series line chart (zoom, pan, hover).
    data: rows from any mcp
    """
    try:
        figure = build_line_chart(data, x_field, y_field, series_field, title)
    except ValueError as e:
        return ToolResult(content =str(e))

    numeric_values = []
    for row in data:
        if y_field in row:
            try:
                numeric_values.append(float(row[y_field]))
            except (TypeError, ValueError):
                pass

    if numeric_values:
        content = (
            f"Rendered a line chart of {y_field} vs {x_field} "
            f"({len(data)} points, range {min(numeric_values):.2f} to {max(numeric_values):.2f})"
        )
    else:
        content = f"Rendered a line chart of {y_field} vs {x_field} ({len(data)} points)."

    return ToolResult(
        content=content, 
        structured_content={"figure": figure},
        meta={"ui": {"resourceUri": VIEW_URI_LINE}, "ui/resourceUri": VIEW_URI_LINE}
    )


VIEW_URI_CANDLESTICK = "ui://graph_mcp/candlestick-chart.html"
VIEW_HTML_CANDLESTICK = (Path(__file__).parent / "views" / "candlestick-dist" / "index.html").read_text()

@mcp.resource(
    VIEW_URI_CANDLESTICK,
    app=AppConfig(csp=ResourceCSP(resource_domains=["https://cdn.plot.ly"]))
)
def candlestick_view() -> str:
    return VIEW_HTML_CANDLESTICK


def _to_float(row, field):
    try:
        return float(row[field])
    except (KeyError, TypeError, ValueError):
        return None



@mcp.tool(app=AppConfig(resource_uri=VIEW_URI_CANDLESTICK))
def generate_candlestick_chart(data: list[dict], x_field: str,
                             open_field: str, high_field: str,
                             low_field: str, close_field: str,
                             title: str = ""):
    """
    Render an interactive candlestick chart (zoom, pan, hover).
    data: rows from any mcp tool
    """
    
    try:
        figure = build_candlestick_chart(data, x_field, open_field, high_field, low_field, close_field, title)
    except ValueError as e:
        return ToolResult(content =str(e))

    highs = [v for v in (_to_float(row, high_field) for row in data) if v is not None]
    lows = [v for v in (_to_float(row, low_field) for row in data) if v is not None]
    first_close = _to_float(data[0], close_field) if data else None
    last_close = _to_float(data[-1], close_field) if data else None

    if highs and lows:
        range_part = f"range {min(lows):.2f} to {max(highs):.2f}"
        if first_close is not None and last_close is not None:
            direction = "up" if last_close > first_close else "down" if last_close < first_close else "flat"
            move_part = f", closed {direction} from {first_close:.2f} to {last_close:.2f}"
        else:
            move_part = ""
        content = f"Rendered a candlestick chart ({len(data)} periods, {range_part}{move_part})."
    else:
        content = f"Rendered a candlestick chart ({len(data)} periods)."
    
    return ToolResult(
        content=content,
        structured_content={"figure": figure},
        meta={"ui": {"resourceUri": VIEW_URI_CANDLESTICK}, "ui/resourceUri": VIEW_URI_CANDLESTICK},
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
    uvicorn.run(app, host="0.0.0.0", port=8002)

