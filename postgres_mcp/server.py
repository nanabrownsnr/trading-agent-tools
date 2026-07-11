import os
from dotenv import load_dotenv
import psycopg
from prefab_ui.components import DataTable, DataTableColumn, Column, Heading
from prefab_ui.app import PrefabApp
from fastmcp import FastMCP
from fastmcp.tools import ToolResult
import logging
import re
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

load_dotenv()

mcp = FastMCP(
    "postgres_mcp",
)

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

def _get_ui_resource_uri(tool_name: str) -> str | None:
    tool = mcp._tool_manager.get_tool(tool_name) 
    if tool and tool.meta:
        return tool.meta.get("ui", {}).get("resourceUri")
    return None

@mcp.tool()
def get_price(commodity: str, exchange: str, start_date: str, end_date: str):
    """Get historical prices for a commodity on a given exchange within a date range."""
    
    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                query = """
                    SELECT * FROM prices 
                    WHERE commodity = %(comm)s 
                    AND exchange = %(exch)s 
                    AND ts BETWEEN %(start)s AND %(end)s;
                """
                params = {
                    "comm": commodity.title(),
                    "exch": exchange.upper(),
                    "start": start_date,
                    "end": end_date,
                }
       
                data = cur.execute(query,params).fetchall()
                logging.info(f"Executing Query: {query} with parameters: {params}")
                logging.info(f"Successfully retrieved {len(data)} records.")
                return {"data": data}
    except psycopg.Error as e:
        logging.error(f"Database query execution failed: {e}")
        return {"error": f"Query failed: {e}"}

@mcp.tool(app=True)
def execute_query(query: str, params: dict):

    """
    Runs a read-only SQL query against the database.
    Only SELECT statements are permitted; results are capped at 1000 rows.

    Example:
        query = "SELECT * FROM prices WHERE commodity = %(comm)s AND ts BETWEEN %(start)s AND %(end)s"
        params = {"comm": "Corn", "start": "2026-07-01", "end": "2026-08-10"}
    """
    
    try:
        safe_query = _enforce_select_only(query)
        safe_query = _apply_row_limit(safe_query)

        try:
            with get_connection() as conn:
                with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    data = cur.execute(safe_query,params).fetchall()
                    logging.info(f"Executing Query: {query} with parameters: {params}")
                    logging.info(f"Successfully retrieved {len(data)} records.")

                    with Column(gap=4, css_class="p-6") as view:
                        Heading(
                            f"Query Results", level=2
                        )

                        if not data:
                            Heading("No records found.", level=4)
                        else:
                            dynamic_columns = [
                                DataTableColumn(
                                    key=k,
                                    header=k.replace("_", " ").title(),
                                    sortable=True,
                                )
                                for k in data[0].keys()
                            ]

                            DataTable(columns=dynamic_columns, rows=data, search=True)

                    compiled_app = PrefabApp(view=view)
                    text_payload = (
                        f"Query returned {len(data)} rows with columns: {', '.join(data[0].keys()) if data else 'none'}."
)
                    resource_uri = _get_ui_resource_uri("execute_query")
                    ui_meta = {"ui": {"resourceUri": resource_uri}} if resource_uri else {}
                    if resource_uri:
                        ui_meta["ui/resourceUri"] = resource_uri

                    return ToolResult(
                    content=text_payload, 
                    structured_content=compiled_app,
                    meta=ui_meta,
                )
                                    
        except psycopg.Error as e:
            logging.error(f"Database query execution failed: {e}")
            return {"error": f"Query failed: {e}"}
    
    except ValueError as e:
        logging.warning(f"Rejected query: {query} — {e}")
        return {"error": str(e)}
    

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
    print(mcp.tools)