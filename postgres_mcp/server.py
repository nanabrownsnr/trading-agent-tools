import os
from dotenv import load_dotenv
import psycopg
from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
import logging
import re
import json
from datetime import datetime
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import statistics


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

load_dotenv()

mcp = FastMCP(
    "postgres_mcp",
)

VIEW_URI = "ui://maps_mcp/dashboard.html"
VIEW_HTML = (Path(__file__).parent / "views" / "dist" / "index.html").read_text(encoding="utf-8")

@mcp.resource(
    VIEW_URI,
    app=AppConfig(csp=ResourceCSP(resource_domains=["https://cdn.plot.ly"],
)))
def dashboard_view():
    return VIEW_HTML

def get_connection():
    conn = None
    try:
        conn = psycopg.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        logging.info("Successfully connected to the database.")
        return conn
    except psycopg.OperationalError as e:
        logging.error(f"Database connection failed: {e}")
        raise

def _enforce_select_only(query: str) -> str:
    """Raise if the query isn't a single, simple SELECT statement."""
    stripped = query.strip().rstrip(";").strip()
    if not re.match(r"^\s*SELECT\s", stripped, re.IGNORECASE):
        raise ValueError("Only SELECT statements are permitted.")
    if ";" in stripped:
        raise ValueError("Multiple statements are not permitted.")
    return stripped

def _apply_row_limit(query: str, max_rows: int = 1000) -> str:
    """Append a LIMIT if the query doesn't already have one."""
    if re.search(r"\bLIMIT\s+\d+\s*$", query, re.IGNORECASE):
        return query
    return f"{query} LIMIT {max_rows}"

@mcp.tool()
def execute_query(query: str, params: dict):
    """
    Runs a read-only SQL query against the database.
    Only SELECT statements are permitted; results are capped at 1000 rows.

    """
    
    safe_query = _enforce_select_only(query)
    safe_query = _apply_row_limit(safe_query)

    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                data = cur.execute(safe_query,params).fetchall()
                print(f"type of query output:{type(data)}")

        return data
                                
    except psycopg.Error as e:
        logging.error(f"Database query execution failed: {e}")
        raise RuntimeError(f"Database query failed: {e}") from e

@mcp.tool()
def get_database_summary():
    """
    Connects to a PostgreSQL database using psycopg (v3) and returns
    a comprehensive summary of schemas, tables, rows, sizes, and keys.
    """

    summary = {
        "database_wide_metrics": {
            "total_tables": 0,
            "total_database_size": "0 bytes"
        },
        "tables": {}
    }    
    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:

                cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;")
                summary["database_wide_metrics"]["total_database_size"] = cur.fetchone()["db_size"]
                

                table_query = """
                    SELECT 
                        n.nspname AS schema_name,
                        c.relname AS table_name,
                        c.reltuples::bigint AS approx_rows,
                        pg_size_pretty(pg_table_size(c.oid)) AS data_size,
                        pg_size_pretty(pg_indexes_size(c.oid)) AS index_size,
                        pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'r' 
                    AND n.nspname = 'public'
                    ORDER BY pg_total_relation_size(c.oid) DESC;
                """
                cur.execute(table_query)
                tables = cur.fetchall()
                summary["database_wide_metrics"]["total_tables"] = len(tables)
                

                column_query = """
                    SELECT 
                        c.table_name,
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                        c.column_default,
                        CASE WHEN tc.constraint_type = 'PRIMARY KEY' THEN tc.constraint_type END as is_pk
                    FROM information_schema.columns c
                    LEFT JOIN information_schema.key_column_usage kcu 
                        ON c.table_name = kcu.table_name 
                        AND c.column_name = kcu.column_name
                    LEFT JOIN information_schema.table_constraints tc 
                        ON kcu.table_name = tc.table_name 
                        AND kcu.constraint_name = tc.constraint_name
                    WHERE c.table_schema = 'public'
                    ORDER BY c.table_name, c.ordinal_position;
                """
                cur.execute(column_query)
                columns_data = cur.fetchall()
                
                for t in tables:
                    t_name = t["table_name"]
                    summary["tables"][t_name] = {
                        "schema": t["schema_name"],
                        "approx_rows": t["approx_rows"],
                        "data_size": t["data_size"],
                        "index_size": t["index_size"],
                        "total_size": t["total_size"],
                        "columns": {}
                    }
                
                for col in columns_data:
                    t_name = col["table_name"]

                    if t_name in summary["tables"]:
                        summary["tables"][t_name]["columns"][col["column_name"]] = {
                            "data_type": col["data_type"],
                            "nullable": col["is_nullable"] == "YES",
                            "default": col["column_default"],
                            "is_primary_key": col["is_pk"] == "PRIMARY KEY"
                        }
                    
        return summary
                                
    except psycopg.Error as e:
        logging.error(f"Database query execution failed: {e}")
        raise RuntimeError(f"Database query failed: {e}") from e


    """Generate a choropleth map for production data."""
    if not production_data:
        return None
    geojson = Maps_MCP_get_location_polygon_geojson(location="West Africa")
    return Maps_MCP_render_choropleth_map(
        layers=[
            {
                "feature": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [...]},
                        "properties": {"name": row["country_name"], "value_quantity": row["production_tonnes"]}
                    }
                    for row in production_data
                ],
                "value_field": "value_quantity"
            }
        ],
        center=[7.95, -1.03],
        zoom=5
    )


def _fetch_prices(commodity):
    """Fetch price data for the given commodity."""
    query = "SELECT * FROM prices WHERE commodity = %s;"
    return execute_query(query, (commodity,))

def _fetch_production(commodity):
    """Fetch production data for the given commodity."""
    query = "SELECT * FROM production WHERE commodity = %s;"
    return execute_query(query, (commodity,))

def _fetch_rainfall():
    """Fetch rainfall data (commodity-agnostic)."""
    query = "SELECT * FROM rainfall;"
    return execute_query(query, ())

def _build_line_chart(data: list[dict], x_field: str, y_field: str, series_field: str | None = None, title: str = ""):
    """
    Price/time series. Pass series_field (e.g. 'commodity') to overlay
    multiple series on one chart — e.g. Corn vs Wheat over the same range.

    Expected data shape: [{"ts": "...", "price": ..., "commodity": "Corn"}, ...]
    """
    df = pd.DataFrame(data)
    missing = {x_field, y_field} - set(df.columns)

    if missing: 
        raise ValueError(f"Missing expected field(S) in data: {missing} ")

    fig = px.line(df, x=x_field, y=y_field, color=series_field, title=title)
    return json.loads(fig.to_json())

def _compute_summary_stats(series: list[float]):
    """
    Compute basic summary statistics for a numeric series.

    Use this when:
    - You want a quick overview of a price or production series.
    - You need mean, median, std, min, max.

    Args:
        series: List of numeric values.

    Returns:
        {
          "count": int,
          "mean": float | None,
          "median": float | None,
          "std": float | None,
          "min": float | None,
          "max": float | None
        }
    """

    clean = [x for x in series if x is not None and not math.isnan(x)]

    count = len(clean)
    mean = statistics.fmean(clean)
    median = statistics.median(clean)
    std = statistics.pstdev(clean) if count > 1 else 0.0
    
    return {
        "count": count,
        "mean": mean,
        "median": median,
        "std": std,
        "min": min(clean),
        "max": max(clean),
    }

@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def show_dashboard(commodity: str):
    """
    Fetches and processes data for a given commodity.
    Returns a structured DashboardState object.
    """

    price_data = _fetch_prices(commodity)
    if not price_data:
        return f"No Price Data for this {commodity}"

    processed_price_data = [
        {**row, 'price': float(row['price'])} for row in price_data
    ]
    
    price_chart = _build_line_chart(
        data=processed_price_data,
        x_field="ts",
        y_field="price",
        title=f"{commodity} Prices"
    )

    price_series = [row["price"] for row in processed_price_data]

    metrics = _compute_summary_stats(price_series)


    production_data = _fetch_production(commodity)
    if not production_data:
        return f"No Production Data for this {commodity}"

    processed_production_data = [
        {**row, 'production_tonnes': float(row['production_tonnes'])} for row in production_data
    ]

    production_chart = _build_line_chart(
        data=processed_production_data,
        x_field="year",
        y_field="production_tonnes",
        series_field="country_name",
        title=f"{commodity} Production Quantity"
    )

    charts = {
        "price_chart": price_chart,
        "production_chart": production_chart
    }

    structured ={
        "commodity":commodity,
        "metrics": metrics,
        "charts": charts
    }
    
    content = f"Rendered report on {commodity} to the canvas."
 
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
    # print("price data:")
    # price_data= _fetch_prices("cocoa")
    # processed_price_data = [
    #     {**row, 'price': float(row['price'])} for row in price_data
    # ]
    
    # price_series = [row["price"] for row in processed_price_data]

    # metrics = _compute_summary_stats(price_series)

    # print(metrics)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)