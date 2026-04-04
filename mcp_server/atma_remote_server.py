import os
from typing import Any, Dict, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

ATMA_BASE_URL = os.getenv("ATMA_BASE_URL")
ATMA_BEARER_TOKEN = os.getenv("ATMA_BEARER_TOKEN")
ATMA_HTTP_TIMEOUT = float(os.getenv("ATMA_HTTP_TIMEOUT", "30"))

if not ATMA_BASE_URL:
    raise RuntimeError("ATMA_BASE_URL must be set")

if not ATMA_BEARER_TOKEN:
    raise RuntimeError("ATMA_BEARER_TOKEN must be set")


mcp = FastMCP("Atma Remote", json_response=True)


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {ATMA_BEARER_TOKEN}",
        "Content-Type": "application/json",
    }


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Any:
    async with httpx.AsyncClient(
        base_url=ATMA_BASE_URL.rstrip("/"),
        timeout=ATMA_HTTP_TIMEOUT,
    ) as client:
        response = await client.request(
            method,
            path,
            headers=_headers(),
            params=params,
            json=json_body,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Atma API error {response.status_code} for {method} {path}: {response.text}"
        )

    if not response.content:
        return {"ok": True}

    return response.json()


def _drop_none(values: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


@mcp.tool()
async def atma_whoami() -> dict:
    """Check which Atma agent identity the MCP server is using."""
    return await _request("GET", "/api/agent/me")


@mcp.tool()
async def atma_list_active_tasks(category: Optional[str] = None) -> list[dict]:
    """List active Atma tasks with computed time remaining."""
    params = _drop_none({"category": category})
    return await _request("GET", "/api/agent/tasks/remainder", params=params)


@mcp.tool()
async def atma_list_overdue_tasks(category: Optional[str] = None) -> list[dict]:
    """List overdue active tasks."""
    params = _drop_none({"category": category})
    return await _request("GET", "/api/agent/tasks/overdue", params=params)


@mcp.tool()
async def atma_list_due_soon_tasks(hours: int = 24, category: Optional[str] = None) -> list[dict]:
    """List tasks due within the next N hours."""
    params = _drop_none({"hours": hours, "category": category})
    return await _request("GET", "/api/agent/tasks/due-soon", params=params)


@mcp.tool()
async def atma_get_domain_summary(hours: int = 24, recent_completion_limit: int = 10) -> dict:
    """Get Atma points and task summary grouped by top-level domain."""
    params = {
        "hours": hours,
        "recent_completion_limit": recent_completion_limit,
    }
    return await _request("GET", "/api/agent/summary/domains", params=params)


@mcp.tool()
async def atma_get_maintenance_snapshot(
    hours: int = 24,
    stale_days: int = 7,
    recent_completion_limit: int = 10,
) -> dict:
    """Get a compact maintenance snapshot for Hermes planning."""
    params = {
        "hours": hours,
        "stale_days": stale_days,
        "recent_completion_limit": recent_completion_limit,
    }
    return await _request("GET", "/api/agent/summary/maintenance", params=params)


@mcp.tool()
async def atma_get_skill_tree() -> dict:
    """Get the Atma skill tree view."""
    return await _request("GET", "/api/agent/skill-tree")


@mcp.tool()
async def atma_list_completed_tasks(limit: int = 20, offset: int = 0) -> list[dict]:
    """List recently completed tasks."""
    params = {"limit": limit, "offset": offset}
    return await _request("GET", "/api/agent/completed", params=params)


@mcp.tool()
async def atma_create_task(
    title: str,
    category: str,
    description: Optional[str] = None,
    priority: int = 3,
    due_date: Optional[str] = None,
    is_recurring: bool = False,
    recurrence_pattern: Optional[str] = None,
) -> dict:
    """Create a new Atma task."""
    body = _drop_none(
        {
            "title": title,
            "description": description,
            "category": category,
            "priority": priority,
            "due_date": due_date,
            "is_recurring": is_recurring,
            "recurrence_pattern": recurrence_pattern,
        }
    )
    return await _request("POST", "/api/agent/tasks", json_body=body)


@mcp.tool()
async def atma_update_task(
    task_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[int] = None,
    due_date: Optional[str] = None,
    is_recurring: Optional[bool] = None,
    recurrence_pattern: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> dict:
    """Update an existing Atma task."""
    body = _drop_none(
        {
            "title": title,
            "description": description,
            "category": category,
            "priority": priority,
            "due_date": due_date,
            "is_recurring": is_recurring,
            "recurrence_pattern": recurrence_pattern,
            "is_active": is_active,
        }
    )
    return await _request("PATCH", f"/api/agent/tasks/{task_id}", json_body=body)


@mcp.tool()
async def atma_complete_task(task_id: int, quality: int = 3, notes: str = "") -> dict:
    """Complete a task in Atma."""
    body = {
        "quality": quality,
        "notes": notes,
    }
    return await _request("POST", f"/api/agent/tasks/{task_id}/complete", json_body=body)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
