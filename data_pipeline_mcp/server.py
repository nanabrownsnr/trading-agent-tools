import os
import time
import requests
from dotenv import load_dotenv
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import jwt

load_dotenv()

AIRBYTE_BASE_URL = os.getenv("AIRBYTE_BASE_URL")
AIRBYTE_CLIENT_ID = os.getenv("AIRBYTE_CLIENT_ID")
AIRBYTE_CLIENT_SECRET = os.getenv("AIRBYTE_CLIENT_SECRET")
AIRBYTE_WORKSPACE_ID = os.getenv("AIRBYTE_WORKSPACE_ID")

_token_cache = {
    "access_token": None,
    "expires_at": 0,
}

def _get_airbyte_token():
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 120:
        return _token_cache["access_token"]

    resp = requests.post(
        f"{AIRBYTE_BASE_URL}applications/token",
        json={
            "client_id": AIRBYTE_CLIENT_ID,
            "client_secret": AIRBYTE_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=10
    )

    resp.raise_for_status()
    data = resp.json()
    access_token = data["access_token"]
    expires_in = data.get("expires_in", 300)

    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = now + expires_in
    
    return access_token

def _airbyte_get(path: str):
    token = _get_airbyte_token()

    headers = {
        "authorization": f"Bearer {token}",
        "accept": "application/json",
    }

    url = f"{AIRBYTE_BASE_URL}{path}"

    resp = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    if resp.status_code == 401:
        token = _get_airbyte_token()
        headers["authorization"] = f"Bearer {token}"

        resp = requests.get(
            url,
            headers=headers,
            timeout=30
        )

    resp.raise_for_status()

    return resp.json()

def _airbyte_post(path: str, json_body: dict | None = None):
    token = _get_airbyte_token()

    headers = {
        "authorization": f"Bearer {token}",
        "accept": "application/json",
        "content-type": "application/json",
    }

    url = f"{AIRBYTE_BASE_URL}{path}"

    resp = requests.post(
        url,
        headers=headers,
        json=json_body
        timeout=30
    )

    if resp.status_code == 401:
        token = _get_airbyte_token()
        headers["authorization"] = f"Bearer {token}"

        resp = requests.post(
            url,
            headers=headers,
            json=json_body
            timeout=30
        )

    if not resp.ok:
        print("Airbyte API Error")
        print("URL:", url)
        print("Status:", resp.status_code)
        print("Response:", resp.text)

    resp.raise_for_status()

    return resp.json()

def _airbyte_patch(path: str, json_body: dict):

    token = _get_airbyte_token()

    headers = {
        "authorization": f"Bearer {token}",
        "accept": "application/json",
        "content-type": "application/json",
    }

    url = f"{AIRBYTE_BASE_URL}{path}"

    resp = requests.patch(
        url,
        json=json_body,
        headers=headers,
        timeout=30,
    )

    if resp.status_code == 401:
        token = _get_airbyte_token()
        headers["authorization"] = f"Bearer {token}"

        resp = requests.patch(
            url,
            json=json_body,
            headers=headers,
            timeout=30,
        )

    if not resp.ok:
        print(resp.status_code)
        print(resp.text)

    resp.raise_for_status()

    return resp.json()


@mcp.tool()
def list_sources():

    return _airbyte_get(f"sources")

@mcp.tool()
def list_connections():

    return _airbyte_get(f"connections")

@mcp.tool()
def get_connection(connection_id: str):

    return _airbyte_get(f"connections/{connection_id}")

@mcp.tool()
def run_connection_sync(connection_id: str):

    return _airbyte_post(
        "jobs",
        {
            "connectionId": connection_id,
            "jobType": "sync"
        }
    )

@mcp.tool()
def get_job_status(connection_id: str):

    jobs = _airbyte_get(f"jobs?connectionId={connection_id}&limit=1")

    latest_job = jobs["data"][0]

    return {
        "status": latest_job["status"],
        "job_id": latest_job["jobId"]
    }

@mcp.tool()
def get_job_logs(job_id: int):

    return _airbyte_get(
        f"/jobs/{job_id}/logs"
    )

@mcp.tool()
def set_connection_schedule(connection_id: str, schedule: dict):

    return _airbyte_patch(
        f"/connections/{connection_id}",
        {
            "schedule": schedule
        }
    )

@mcp.tool()
def pause_connection(connection_id: str):

    return _airbyte_patch(
        f"/connections/{connection_id}",
        {
            "status": "inactive"
        }
    )

@mcp.tool()
def resume_connection(connection_id: str):

    return _airbyte_patch(
        f"/connections/{connection_id}",
        {
            "status": "active"
        }
    )


middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["mcp-protocol-version", "mcp-session-id", "Authorization", "Content-Type"],
        expose_headers=["mcp-session-id"],
    )
]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host= "0.0.0.0", port= 8006)