from pathlib import Path
from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from charts import build_line_chart


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
    summary = (
        f"Rendered a line chart of {y_field} vs {x_field} "
        f"({len(data)} points, {min(values):.2f} to {max(values):.2f})"
        if values else f"No data to plot for '{y_field}'."
    )
    return ToolResult(content=summary, structured_content={"figure": figure})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)

