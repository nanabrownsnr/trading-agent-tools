import { App } from "@modelcontextprotocol/ext-apps";

const app = new App({ name: "dashboard", version: "1.0.0" });

function renderMetrics(metrics) {
    const container = document.getElementById("metrics");
    container.innerHTML = "";

    // First row (e.g., price metrics)
    const row1 = document.createElement("div");
    row1.className = "metric-card";
    row1.innerHTML = `
    <h3>Price Metrics</h3>
    <p><strong>Count:</strong> ${metrics.count}</p>
    <p><strong>Mean:</strong> ${metrics.mean}</p>
    <p><strong>Median:</strong> ${metrics.median}</p>
    <p><strong>Std:</strong> ${metrics.std}</p>
  `;
    container.appendChild(row1);

}

function renderGraphs(charts) {
    const container = document.getElementById("graphs");
    container.innerHTML = "";

    // Price Chart
    const priceCard = document.createElement("div");
    priceCard.className = "graph-card";
    priceCard.innerHTML = `<div id="price-chart" style="width: 100%; height: 300px;"></div>`;
    container.appendChild(priceCard);

    // Production Chart
    const productionCard = document.createElement("div");
    productionCard.className = "graph-card";
    productionCard.innerHTML = `<div id="production-chart" style="width: 100%; height: 300px;"></div>`;
    container.appendChild(productionCard);

    // Render charts using Plotly
    if (charts.price_chart) {
        Plotly.newPlot("price-chart", charts.price_chart.data, charts.price_chart.layout, { responsive: true });
    }
    if (charts.production_chart) {
        Plotly.newPlot("production-chart", charts.production_chart.data, charts.production_chart.layout, { responsive: true });
    }
}


app.ontoolresult = (result) => {
    const data = result.structuredContent;

    renderMetrics(data.metrics);

    renderGraphs(data.charts);
};

app.connect();
