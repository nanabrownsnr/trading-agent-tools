import { App } from "@modelcontextprotocol/ext-apps";
const app = new App({ name: "graph-mcp-line-chart", version: "1.0.0" });
app.ontoolresult = (result) => {
    const figure = result.structuredContent?.figure;
    if (figure) Plotly.newPlot("chart", figure.data, figure.layout, { responsive: true });
};
app.connect();