import os
from dotenv import load_dotenv
import requests
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

AIRBYTE_BASE_URL = os.getenv("AIRBYTE_BASE_URL", "https://api.airbyte.com/v1")
AIRBYTE_API_KEY = os.getenv("AIRBYTE_API_KEY", "")
AIRBYTE_WORKSPACE_ID=os.getenv("AIRBYTE_WORKSPACE_ID", "")

if not AIRBYTE_API_KEY:
    raise RuntimeError("Set AIRBYTE_API_KEY in your environment before running this MCP server.")

HEADERS = {
    "Authorization": f"Bearer {AIRBYTE_API_KEY}",
    "accept": "application/json",
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
def list_workspaces():
    """
    List all avilable workspaces
    
    Returns:
        Workspace details.
    """
    
    data = _airbyte_get("/workspaces")
    
    return data

@mcp.tool
def list_sources():
    """
    List Airbyte sources (pipelines).

    """

    data = _airbyte_get("/sources")

    return data


@mcp.tool
def get_sources_details(sourceID: str):
    """
    Get Airbyte sources details(pipelines).
    """
    data = _airbyte_get("/sources",{"sourceId":sourceID})

    return data

# @mcp.tool
# def get_workspace_info(workspace_id: str | None = None) -> dict:
#     """
#     Get information about a workspace.
    
#     Args:
#         workspace_id: Optional workspace ID (defaults to env var)
    
#     Returns:
#         Workspace details.
#     """
#     ws_id = workspace_id or os.getenv("AIRBYTE_WORKSPACE_ID")
#     if not ws_id:
#         raise RuntimeError("Set AIRBYTE_WORKSPACE_ID in your environment.")
    
#     data = _airbyte_get("/workspaces", {"workspaceId": ws_id})
    
#     return {
#         "id": data.get("workspaceId"),
#         "name": data.get("name"),
#         "organization_id": data.get("organizationId"),
#     }

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