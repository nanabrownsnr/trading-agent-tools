from fastmcp import FastMCP, ToolResult
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Heading
from prefab_ui.components.charts import LineChart, ChartSeries

mcp = FastMCP("graph-mcp")

@mcp.tool(app=True)
def generate_line_chart(data: list[dict], x_field: str, y_field: str,
                         series_field: str | None = None, title: str = "") -> ToolResult:
    """
    Render a price/time-series line chart. Interactive natively (hover
    tooltips, legend toggling). data: rows from any db-mcp, e.g. get_price
    output. If series_field is set (e.g. 'commodity'), multiple commodities
    overlay on one chart.
    """
    with Column(gap=4, css_class="p-6") as view:
        if title:
            Heading(title)
        LineChart(
            data=data,
            series=[ChartSeries(data_key=y_field, label=y_field)],
            x_axis=x_field,
            show_legend=True,
        )
    return ToolResult(content=data, structured_content=view)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)

