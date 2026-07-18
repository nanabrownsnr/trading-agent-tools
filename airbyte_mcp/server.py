from dotenv import load_dotenv
import requests
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

AIRBYTE_BASE_URL = os.getenv("AIRBYTE_BASE_URL", "https://api.airbyte.com/v1")
AIRBYTE_API_KEY = os.getenv("AIRBYTE_API_KEY", "")

if not AIRBYTE_API_KEY:
    raise RuntimeError("Set AIRBYTE_API_KEY in your environment before running this MCP server.")

HEADERS = {
    "Authorization": f"Bearer {AIRBYTE_API_KEY}",
    "Content-Type": "application/json",
}


def _airbyte_get(path: str, params: dict | None = None):
    url = f"{AIRBYTE_BASE_URL}{path}"
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def _airbyte_post(path: str, payload: dict):
    url = f"{AIRBYTE_BASE_URL}{path}"
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


mcp = FastMCP("airbyte_mcp")

@mcp.tool
def list_pipelines(search: str | None = None, status: str | None = None) -> list[dict]:
    """
    List Airbyte connections (pipelines).

    Args:
        search: Optional substring to filter by name.
        status: Optional status filter (e.g., 'active', 'inactive').

    Returns:
        A list of connections with basic metadata.
    """
    # NOTE: Adjust endpoint/shape based on your Airbyte version.
    # For Cloud v1, there is usually a /connections/list or similar.
    # Here we assume a POST /connections/list with workspace_id, etc.
    # Replace WORKSPACE_ID with your actual workspace ID or pass it via env.
    workspace_id = os.getenv("AIRBYTE_WORKSPACE_ID")
    if not workspace_id:
        raise RuntimeError("Set AIRBYTE_WORKSPACE_ID in your environment.")

    data = _airbyte_post("/connections/list", {"workspaceId": workspace_id})
    connections = data.get("connections", [])

    results = []
    for c in connections:
        name = c.get("name") or c.get("connectionId")
        conn_status = c.get("status")
        if search and search.lower() not in str(name).lower():
            continue
        if status and conn_status and status.lower() != conn_status.lower():
            continue

        results.append(
            {
                "id": c.get("connectionId"),
                "name": name,
                "status": conn_status,
                "source_id": c.get("sourceId"),
                "destination_id": c.get("destinationId"),
                "schedule": c.get("scheduleType"),
            }
        )

    return results

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["mcp-protocol-version", "mcp-session-id", "Authorization", "Content-Type"],
        expose_headers=["mcp-session-id"],
    )
]
app = mcp.http_app(middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)