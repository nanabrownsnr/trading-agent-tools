import os
from dotenv import load_dotenv
import psycopg
from fastmcp import FastMCP
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
            

        return {"data": data}
                                
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
            # 1. Fetch Database-Wide Metrics
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;")
            summary["database_wide_metrics"]["total_database_size"] = cur.fetchone()["db_size"]
            
            # 2. Fetch Comprehensive Table Profiles (Rows, Sizes, Descriptions)
            # Uses pg_class for lightning-fast approximate row counts without locking tables
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
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY pg_total_relation_size(c.oid) DESC;
            """
            cur.execute(table_query)
            tables = cur.fetchall()
            summary["database_wide_metrics"]["total_tables"] = len(tables)
            
            # 3. Fetch Column Details, Primary Keys, and Nullability mapping
            # This query grabs all column properties in one structured sweep
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
                WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY c.table_name, c.ordinal_position;
            """
            cur.execute(column_query)
            columns_data = cur.fetchall()
            
            # 4. Synthesize data structures into the summary dictionary
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
                # Safeguard in case columns exist for tables missed in the physical filter
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


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)