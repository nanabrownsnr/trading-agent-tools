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
            

        return ["data": data]
                                
    except psycopg.Error as e:
        logging.error(f"Database query execution failed: {e}")
        raise RuntimeError(f"Database query failed: {e}") from e
    

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
    print(mcp.tools)