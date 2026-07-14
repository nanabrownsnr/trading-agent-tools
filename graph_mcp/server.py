from pathlib import Path
from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from charts import build_line_chart, build_candlestick_chart, build_dual_axis_chart
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

mcp = FastMCP("graph-mcp")

VIEW_URI = "ui://graph_mcp/chart.html"
VIEW_HTML = (Path(__file__).parent / "views" / "dist" / "index.html").read_text()

@mcp.resource(
    VIEW_URI,
    app=AppConfig(csp=ResourceCSP(
        resource_domains=["https://cdn.plot.ly"],
    ))
)
def line_chart_view() -> str:
    return VIEW_HTML

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
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
        structured_content=figure,
        meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI}
    )

def _to_float(row, field):
    try:
        return float(row[field])
    except (KeyError, TypeError, ValueError):
        return None

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def generate_candlestick_chart(data: list[dict], x_field: str,
                             open_field: str, high_field: str,
                             low_field: str, close_field: str,
                             title: str = "") -> ToolResult:
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
        structured_content=figure,
        meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI},
    )

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def generate_dual_axis_chart(data: list[dict], x_field: str,
                           y1_field: str, y2_field: str,
                           y1_label: str | None = None, y2_label: str | None = None,
                           title: str = "") -> ToolResult:
    """
    Render an interactive dualaxis chart (zoom, pan, hover).
    data: rows from any mcp tool
    """
    
    try:
        figure = build_dual_axis_chart(data, x_field, y1_field, y2_field, y1_label, y2_label, title)
    except ValueError as e:
        return ToolResult(content =str(e))

    y1_values = [v for v in (_to_float(row, y1_field) for row in data) if v is not None]
    y2_values = [v for v in (_to_float(row, y2_field) for row in data) if v is not None]

    if y1_values and y2_values:
        y1_range = f"{min(y1_values):.2f} to {max(y1_values):.2f}"
        y2_range = f"{min(y2_values):.2f} to {max(y2_values):.2f}"

        y1_direction = "up" if y1_values[-1] > y1_values[0] else "down" if y1_values[-1] < y1_values[0] else "flat"
        y2_direction = "up" if y2_values[-1] > y2_values[0] else "down" if y2_values[-1] < y2_values[0] else "flat"
        relationship = "moved together" if y1_direction == y2_direction else "diverged"

        label1 = y1_label or y1_field
        label2 = y2_label or y2_field
        content = (
            f"Rendered a dual-axis chart of {label1} ({y1_range}, {y1_direction}) "
            f"vs {label2} ({y2_range}, {y2_direction}) over {len(data)} points — the two series {relationship}."
        )
    else:
        content = f"Rendered a dual-axis chart of {y1_field} vs {y2_field} ({len(data)} points)."
    
    return ToolResult(
        content=content,
        structured_content=figure,
        meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI},
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

