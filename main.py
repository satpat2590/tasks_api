 # main.py
import calendar
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import Client, create_client
from dotenv import load_dotenv
from utils.auth import AgentPrincipal, require_read_agent, require_write_agent
from utils.data import (
    CompletionActionResponse,
    CompletionData,
    CompletionResponse,
    CompletionUpdate,
    DomainSummaryItem,
    DomainSummaryResponse,
    DomainSummaryTotals,
    MaintenanceSnapshotResponse,
    TaskCreate,
    TaskRemainderResponse,
    TaskResponse,
    TaskUpdate,
)
from utils.tags import auto_tag_task

# Set up the FastAPI backend. Use uvicorn as your web server (preferably)
app = FastAPI()

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ACCESS_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_ACCESS_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY or SUPABASE_API_KEY must be set")

# Make the connection to Supabase instance
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_ACCESS_KEY
)

DEFAULT_CATEGORIES = ("mental", "physical", "social", "financial")
DEFAULT_DUE_SOON_HOURS = 24
DEFAULT_STALE_DAYS = 7

# CORS for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sbpatel.dev", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamps from Supabase into timezone-aware datetimes."""
    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def due_sort_key(task: Dict) -> datetime:
    due_date = parse_datetime(task.get("due_date"))
    return due_date or datetime.max.replace(tzinfo=timezone.utc)


def with_time_remaining(task: Dict, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now(timezone.utc)
    enriched = dict(task)
    due_date = parse_datetime(task.get("due_date"))
    if due_date:
        enriched["time_remaining"] = int((due_date - now).total_seconds() // 3600)
    else:
        enriched["time_remaining"] = None
    return enriched


def fetch_tasks(active_only: bool = False) -> List[Dict]:
    query = supabase.table("tasks").select("*")
    if active_only:
        query = query.eq("is_active", True)
    response = query.execute()
    return response.data or []


def filter_tasks_by_category(tasks: List[Dict], category: Optional[str]) -> List[Dict]:
    if not category:
        return tasks
    return [task for task in tasks if task.get("category") == category]


def classify_active_tasks(tasks: List[Dict], due_soon_hours: int, now: Optional[datetime] = None):
    now = now or datetime.now(timezone.utc)
    due_soon_cutoff = now + timedelta(hours=due_soon_hours)

    overdue = []
    due_soon = []
    no_due_date = []

    for task in tasks:
        due_date = parse_datetime(task.get("due_date"))
        if not due_date:
            no_due_date.append(task)
            continue
        if due_date < now:
            overdue.append(task)
        elif due_date <= due_soon_cutoff:
            due_soon.append(task)

    overdue.sort(key=due_sort_key)
    due_soon.sort(key=due_sort_key)
    no_due_date.sort(key=lambda task: task.get("id", 0))
    return overdue, due_soon, no_due_date


def fetch_completion_rows(limit: Optional[int] = None, offset: int = 0) -> List[Dict]:
    query = supabase.table("task_completions").select(
        "*, tasks(title, category)"
    ).order("completed_at", desc=True)
    if limit is not None:
        query = query.range(offset, offset + limit - 1)
    response = query.execute()
    return response.data or []


def transform_completion_rows(rows: List[Dict]) -> List[Dict]:
    completions = []
    for item in rows:
        task_info = item.get("tasks") or {}
        completions.append(
            {
                "id": item["id"],
                "task_id": item["task_id"],
                "task_title": task_info.get("title", "Unknown Task"),
                "task_category": task_info.get("category", "unknown"),
                "completed_at": item["completed_at"],
                "notes": item.get("notes"),
                "was_late": item.get("was_late", False),
                "time_spent_minutes": item.get("time_spent_minutes"),
                "points": item.get("points", 0) or 0,
            }
        )
    return completions


def fetch_recent_completions(limit: int = 10) -> List[Dict]:
    return transform_completion_rows(fetch_completion_rows(limit=limit))


def calculate_points(task_data: Dict, quality_score: int, was_late: bool) -> int:
    base_points = (task_data.get("priority") or 0) * 10

    recurrence_pattern = (task_data.get("recurrence_pattern") or "").lower()
    if task_data.get("is_recurring") and "daily" in recurrence_pattern:
        base_points = int(base_points * 0.3)

    if quality_score >= 4:
        base_points = int(base_points * 1.2)
    elif quality_score <= 2:
        base_points = int(base_points * 0.8)

    if was_late:
        base_points = -base_points

    return base_points


def add_months(current_due: datetime, months: int) -> datetime:
    month_index = current_due.month - 1 + months
    year = current_due.year + month_index // 12
    month = month_index % 12 + 1
    day = min(current_due.day, calendar.monthrange(year, month)[1])
    return current_due.replace(year=year, month=month, day=day)


def add_years(current_due: datetime, years: int) -> datetime:
    target_year = current_due.year + years
    day = min(current_due.day, calendar.monthrange(target_year, current_due.month)[1])
    return current_due.replace(year=target_year, day=day)


def calculate_next_due_date(current_due: datetime, pattern: Optional[str]) -> datetime:
    normalized = (pattern or "").strip().lower()

    if normalized == "daily":
        return current_due + timedelta(days=1)
    if normalized == "weekly":
        return current_due + timedelta(weeks=1)
    if normalized == "monthly":
        return add_months(current_due, 1)
    if normalized == "yearly":
        return add_years(current_due, 1)

    match = re.match(r"every (\d+) days?", normalized)
    if match:
        return current_due + timedelta(days=int(match.group(1)))

    match = re.match(r"every (\d+) weeks?", normalized)
    if match:
        return current_due + timedelta(weeks=int(match.group(1)))

    return current_due + timedelta(weeks=1)


def complete_task_record(task_id: int, completion_data: Optional[CompletionData]) -> Dict:
    task_response = supabase.table("tasks").select("*").eq("id", task_id).execute()
    if not task_response.data:
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = task_response.data[0]
    completed_at = datetime.now(timezone.utc)
    due_date = parse_datetime(task_data.get("due_date"))
    was_late = bool(due_date and completed_at > due_date)
    overdue_minutes = 0
    if due_date and was_late:
        overdue_minutes = int((completed_at - due_date).total_seconds() // 60)

    quality_score = completion_data.quality if completion_data and completion_data.quality is not None else 3
    notes = completion_data.notes if completion_data and completion_data.notes is not None else ""
    points_earned = calculate_points(task_data, quality_score, was_late)

    completion_record = {
        "task_id": task_id,
        "completion_quality": quality_score,
        "notes": notes,
        "was_late": was_late,
        "time_spent_minutes": overdue_minutes,
        "points": points_earned,
        "completed_at": completed_at.isoformat(),
    }
    supabase.table("task_completions").insert(completion_record).execute()

    if not task_data.get("is_recurring"):
        supabase.table("tasks").update({"is_active": False}).eq("id", task_id).execute()
        return {
            "message": f"Task completed! {points_earned} points",
            "task_id": task_id,
            "completed_at": completed_at,
            "points_earned": points_earned,
            "is_recurring": False,
            "next_due": None,
        }

    next_due = calculate_next_due_date(due_date or completed_at, task_data.get("recurrence_pattern"))
    supabase.table("tasks").update({"due_date": next_due.isoformat(), "is_active": True}).eq("id", task_id).execute()
    return {
        "message": f"Recurring task completed! {points_earned} points. Next due: {next_due.date()}",
        "task_id": task_id,
        "completed_at": completed_at,
        "points_earned": points_earned,
        "is_recurring": True,
        "next_due": next_due,
    }


def collect_category_set(tasks: List[Dict], completion_rows: List[Dict]) -> List[str]:
    categories = set(DEFAULT_CATEGORIES)
    categories.update(task.get("category") for task in tasks if task.get("category"))
    categories.update((row.get("tasks") or {}).get("category") for row in completion_rows if row.get("tasks"))
    return [category for category in DEFAULT_CATEGORIES if category in categories] + sorted(
        category for category in categories if category and category not in DEFAULT_CATEGORIES
    )


def build_domain_summary_payload(due_soon_hours: int = DEFAULT_DUE_SOON_HOURS, recent_completion_limit: int = 10) -> Dict:
    now = datetime.now(timezone.utc)
    tasks = fetch_tasks(active_only=False)
    active_tasks = [task for task in tasks if task.get("is_active")]
    overdue_tasks, due_soon_tasks, _ = classify_active_tasks(active_tasks, due_soon_hours, now)
    completion_rows = fetch_completion_rows()
    categories = collect_category_set(tasks, completion_rows)

    active_counts = Counter(task["category"] for task in active_tasks if task.get("category"))
    overdue_counts = Counter(task["category"] for task in overdue_tasks if task.get("category"))
    due_soon_counts = Counter(task["category"] for task in due_soon_tasks if task.get("category"))
    recurring_counts = Counter(
        task["category"]
        for task in active_tasks
        if task.get("category") and task.get("is_recurring")
    )
    completed_counts = Counter()
    points_by_category = Counter()
    last_completed_at: Dict[str, Optional[datetime]] = {}

    for row in completion_rows:
        task_info = row.get("tasks") or {}
        category = task_info.get("category")
        if not category:
            continue
        completed_counts[category] += 1
        points_by_category[category] += row.get("points", 0) or 0
        completed_at = parse_datetime(row.get("completed_at"))
        if completed_at and (
            category not in last_completed_at or completed_at > last_completed_at[category]
        ):
            last_completed_at[category] = completed_at

    domains = []
    for category in categories:
        domains.append(
            DomainSummaryItem(
                category=category,
                active_tasks=active_counts.get(category, 0),
                overdue_tasks=overdue_counts.get(category, 0),
                due_soon_tasks=due_soon_counts.get(category, 0),
                recurring_tasks=recurring_counts.get(category, 0),
                completed_tasks=completed_counts.get(category, 0),
                total_points=points_by_category.get(category, 0),
                last_completed_at=last_completed_at.get(category),
            ).model_dump()
        )

    totals = DomainSummaryTotals(
        active_tasks=len(active_tasks),
        overdue_tasks=len(overdue_tasks),
        due_soon_tasks=len(due_soon_tasks),
        recurring_tasks=sum(1 for task in active_tasks if task.get("is_recurring")),
        completed_tasks=len(completion_rows),
        total_points=sum(points_by_category.values()),
    ).model_dump()

    return DomainSummaryResponse(
        generated_at=now,
        due_soon_window_hours=due_soon_hours,
        totals=totals,
        domains=domains,
        recent_completions=fetch_recent_completions(recent_completion_limit),
    ).model_dump()


def build_maintenance_snapshot_payload(
    due_soon_hours: int = DEFAULT_DUE_SOON_HOURS,
    stale_after_days: int = DEFAULT_STALE_DAYS,
    recent_completion_limit: int = 10,
) -> Dict:
    now = datetime.now(timezone.utc)
    active_tasks = fetch_tasks(active_only=True)
    overdue_tasks, due_soon_tasks, no_due_date_tasks = classify_active_tasks(active_tasks, due_soon_hours, now)
    task_tags = supabase.table("task_tags").select("*").execute().data or []
    tagged_task_ids = {row["task_id"] for row in task_tags}
    stale_cutoff = now - timedelta(days=stale_after_days)

    untagged_active_tasks = [task for task in active_tasks if task.get("id") not in tagged_task_ids]
    stale_active_tasks = [
        task
        for task in active_tasks
        if parse_datetime(task.get("updated_at")) and parse_datetime(task.get("updated_at")) < stale_cutoff
    ]

    completion_rows = fetch_completion_rows()
    points_by_category = Counter()
    for row in completion_rows:
        task_info = row.get("tasks") or {}
        category = task_info.get("category")
        if category:
            points_by_category[category] += row.get("points", 0) or 0

    return MaintenanceSnapshotResponse(
        generated_at=now,
        due_soon_window_hours=due_soon_hours,
        stale_after_days=stale_after_days,
        counts={
            "active_tasks": len(active_tasks),
            "overdue_tasks": len(overdue_tasks),
            "due_soon_tasks": len(due_soon_tasks),
            "tasks_without_due_date": len(no_due_date_tasks),
            "untagged_active_tasks": len(untagged_active_tasks),
            "stale_active_tasks": len(stale_active_tasks),
            "recurring_tasks": sum(1 for task in active_tasks if task.get("is_recurring")),
            "completed_tasks": len(completion_rows),
        },
        active_by_category=dict(Counter(task["category"] for task in active_tasks if task.get("category"))),
        overdue_by_category=dict(Counter(task["category"] for task in overdue_tasks if task.get("category"))),
        due_soon_by_category=dict(Counter(task["category"] for task in due_soon_tasks if task.get("category"))),
        points_by_category=dict(points_by_category),
        overdue_tasks=[with_time_remaining(task, now) for task in overdue_tasks],
        due_soon_tasks=[with_time_remaining(task, now) for task in due_soon_tasks],
        untagged_active_tasks=[with_time_remaining(task, now) for task in sorted(untagged_active_tasks, key=due_sort_key)],
        stale_active_tasks=[with_time_remaining(task, now) for task in sorted(stale_active_tasks, key=due_sort_key)],
        recent_completions=fetch_recent_completions(recent_completion_limit),
    ).model_dump()


######## Endpoint implementation for our lovely web server API ###########
@app.get("/")
def read_root():
    return {"message": "Infinite Domain: Satyam's Call Center"}

@app.head("/")
async def head_root():
    """
    Handles HEAD requests for the root path.
    This is often used for health checks.
    """
    return  # Returning nothing (or an empty string) is sufficient for HEAD (exquisite dome)


@app.get("/api/agent/me")
async def get_authenticated_agent(agent: AgentPrincipal = Depends(require_read_agent)):
    """Return the authenticated agent principal for integration testing."""
    return {
        "agent": agent.name,
        "scopes": sorted(agent.scopes),
    }


@app.get("/api/tasks", response_model=List[TaskResponse])
async def get_active_tasks():
    """
        Retrieve all active tasks

        :request: NONE
        :response: A list of TaskResponse objects
    """
    tasks = fetch_tasks(active_only=True)
    tasks.sort(key=due_sort_key)
    return tasks

@app.get("/api/tasks/remainder", response_model=List[TaskRemainderResponse])
async def get_tasks_with_remainder(category: Optional[str] = None):
    """
    Retrieve all active tasks with calculated time remaining in hours
    """
    now = datetime.now(timezone.utc)
    tasks = filter_tasks_by_category(fetch_tasks(active_only=True), category)
    tasks.sort(key=due_sort_key)
    return [with_time_remaining(task, now) for task in tasks]


@app.get("/api/tasks/overdue", response_model=List[TaskRemainderResponse])
async def get_overdue_tasks(category: Optional[str] = None):
    """Retrieve active tasks with due dates in the past."""
    now = datetime.now(timezone.utc)
    tasks = filter_tasks_by_category(fetch_tasks(active_only=True), category)
    overdue_tasks, _, _ = classify_active_tasks(tasks, DEFAULT_DUE_SOON_HOURS, now)
    return [with_time_remaining(task, now) for task in overdue_tasks]


@app.get("/api/tasks/due-soon", response_model=List[TaskRemainderResponse])
async def get_due_soon_tasks(
    hours: int = Query(DEFAULT_DUE_SOON_HOURS, ge=1, le=168),
    category: Optional[str] = None,
):
    """Retrieve active tasks due within the requested number of hours."""
    now = datetime.now(timezone.utc)
    tasks = filter_tasks_by_category(fetch_tasks(active_only=True), category)
    _, due_soon_tasks, _ = classify_active_tasks(tasks, hours, now)
    return [with_time_remaining(task, now) for task in due_soon_tasks]

@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(task: TaskCreate):
    """
        Create a new task using the TaskCreate data definition in /utils/data.py

        :request: A TaskCreate object
        :response: A TaskResponse object
    """
    try:
        response = supabase.table('tasks').insert({
            "title": task.title,
            "description": task.description,
            "category": task.category,
            "priority": task.priority,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "is_recurring": task.is_recurring,
            "recurrence_pattern": task.recurrence_pattern
        }).execute()

     # Retrieve task ID to place within task_tags table
        task_id = response.data[0]['id']

     # Auto-tag with AI, but do not fail task creation if tagging is unavailable
        try:
            tags = await auto_tag_task(response.data[0])
            print("\nThe list of leaf-node tag IDs:", tags)
            for tag_id in tags:
                supabase.table('task_tags').insert({
                    'task_id': task_id,
                    'tag_id': tag_id
                }).execute()
        except Exception as tagging_error:
            print(f"[WARN] Auto-tagging failed for task_id={task_id}: {tagging_error}")

        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task: TaskUpdate,
):
    """
        Update fields of a task based on the TaskUpdate data definition in /utils/data.py

        :request: A TaskUpdate object
        :response: A TaskResponse object with the new fields of the updated task
    """
    try:
     # Populate the JSON request body so that you can update the fields in the row for the task_id
        update_data = {}
        if task.title is not None:
            update_data["title"] = task.title
        if task.description is not None:
            update_data["description"] = task.description
        if task.category is not None:
            update_data["category"] = task.category
        if task.priority is not None:
            update_data["priority"] = task.priority
        if task.due_date is not None:
            update_data["due_date"] = task.due_date.isoformat()
        if task.is_recurring is not None:
            update_data["is_recurring"] = task.is_recurring
        if task.recurrence_pattern is not None:
            update_data["recurrence_pattern"] = task.recurrence_pattern
        if task.is_active is not None:
            update_data["is_active"] = task.is_active
        
        # Always update the updated_at timestamp
     # DISABLED SINCE THERE IS A TRIGGER IN THE DATABASE WHICH AUTOMATICALLY UPDATES THE 'updated_at' FIELD ON UPDATE QUERIES
        #update_data["updated_at"] = datetime.now().isoformat()
        
        response = supabase.table('tasks').update(update_data).eq('id', task_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Task not found")
            
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tasks/{task_id}/complete", response_model=CompletionActionResponse)
async def complete_task(
    task_id: int,
    completion_data: Optional[CompletionData] = None,
):
    """Complete a task, log the completion, and advance recurrence if needed."""
    try:
        return complete_task_record(task_id, completion_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/tasks/disable/{task_id}", response_model=CompletionActionResponse)
async def disable_task(
    task_id: int,
    completion_data: Optional[CompletionData] = None,
):
    """
    Complete task - log completion and handle recurring tasks
    
    Optional request body:
    {
        "quality": 1-5,
        "notes": "string"
    }
    """
    try:
        return complete_task_record(task_id, completion_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@app.delete("/api/tasks/{task_id}")
async def hard_delete_task(task_id: int):
    """
        Hard delete a task from the table entirely

        :request: NONE
        :response: Message verifying that task was permanently removed from table
    """
    try:
     # Check if task exists
        existing_task = supabase.table('tasks').select("*").eq('id', task_id).execute()
        if not existing_task.data:
            raise HTTPException(status_code=404, detail="Task not found")

     # Delete dependent records first (optional)
        supabase.table('notifications').delete().eq('task_id', task_id).execute()
        supabase.table('task_completions').delete().eq('task_id', task_id).execute()
        supabase.table('task_tags').delete().eq('task_id', task_id).execute()

     # Finally, delete the task
        supabase.table('tasks').delete().eq('id', task_id).execute()

        return {"message": "Task and all related records permanently deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

####################### /api/completed

@app.get("/api/completed", response_model=List[CompletionResponse])
async def get_completed_tasks(
    limit: int = 50,
    offset: int = 0,
):
    """Get completed tasks with task details"""
    rows = fetch_completion_rows(limit=limit, offset=offset)
    return transform_completion_rows(rows)

@app.patch("/api/completed/{completion_id}")
async def update_completion_notes(
    completion_id: int,
    update: CompletionUpdate,
):
    """Update notes for a completed task"""
    response = supabase.table('task_completions').update({
        "notes": update.notes
    }).eq('id', completion_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Completion not found")
    
    return {"message": "Notes updated"}


@app.get("/api/summary/domains", response_model=DomainSummaryResponse)
async def get_domain_summary(
    hours: int = Query(DEFAULT_DUE_SOON_HOURS, ge=1, le=168),
    recent_completion_limit: int = Query(10, ge=1, le=50),
):
    """Return an LLM-friendly breakdown of task and points state by top-level domain."""
    return build_domain_summary_payload(hours, recent_completion_limit)


@app.get("/api/summary/maintenance", response_model=MaintenanceSnapshotResponse)
async def get_maintenance_snapshot(
    hours: int = Query(DEFAULT_DUE_SOON_HOURS, ge=1, le=168),
    stale_days: int = Query(DEFAULT_STALE_DAYS, ge=1, le=90),
    recent_completion_limit: int = Query(10, ge=1, le=50),
):
    """Return a compact operational view for an LLM or MCP wrapper."""
    return build_maintenance_snapshot_payload(hours, stale_days, recent_completion_limit)


######## SKILL TREE VISUALIZATION

@app.get("/api/skill-tree")
async def get_skill_tree():
    """Get hierarchical skill tree with points"""
    tags = supabase.table("tags").select("*").execute().data or []
    tasks = supabase.table("tasks").select("id, category").execute().data or []
    task_tag_rows = supabase.table("task_tags").select("*").execute().data or []
    completion_rows = supabase.table("task_completions").select("task_id, points").execute().data or []

    tags_by_id = {tag["id"]: tag for tag in tags}
    children_by_parent = defaultdict(list)
    for tag in tags:
        children_by_parent[tag.get("parent_tag_id")].append(tag)

    task_category_by_id = {task["id"]: task.get("category") for task in tasks}
    task_tags_map = defaultdict(list)
    for row in task_tag_rows:
        task_tags_map[row["task_id"]].append(row["tag_id"])

    path_cache: Dict[int, str] = {}

    def get_local_tag_path(tag_id: int) -> str:
        if tag_id in path_cache:
            return path_cache[tag_id]

        parts = []
        current_id = tag_id
        while current_id:
            tag = tags_by_id.get(current_id)
            if not tag:
                break
            parts.insert(0, tag["name"])
            current_id = tag.get("parent_tag_id")

        path_cache[tag_id] = "/".join(parts)
        return path_cache[tag_id]

    task_counts = Counter()
    tag_points = defaultdict(float)
    category_points = Counter()

    for completion in completion_rows:
        task_id = completion["task_id"]
        points = completion.get("points", 0) or 0
        category = task_category_by_id.get(task_id)
        if category:
            category_points[category] += points

        tag_ids = task_tags_map.get(task_id, [])
        if not tag_ids:
            continue

        split_points = points / len(tag_ids)
        for tag_id in tag_ids:
            tag_path = get_local_tag_path(tag_id)
            task_counts[tag_path] += 1
            tag_points[tag_path] += split_points

    def build_tag_node(tag: Dict) -> Dict:
        tag_path = get_local_tag_path(tag["id"])
        node = {
            "name": tag["name"],
            "points": round(tag_points.get(tag_path, 0.0), 2),
            "completed_tasks": task_counts.get(tag_path, 0),
            "path": tag_path,
            "children": [],
        }

        for child in sorted(children_by_parent.get(tag["id"], []), key=lambda item: item["name"]):
            child_node = build_tag_node(child)
            node["children"].append(child_node)
            node["completed_tasks"] += child_node["completed_tasks"]

        return node

    root = {
        "name": "All Skills",
        "points": sum(category_points.values()),
        "completed_tasks": len(completion_rows),
        "children": [],
    }

    available_categories = sorted({tag["category"] for tag in tags if tag.get("category")})
    categories = [category for category in DEFAULT_CATEGORIES if category in available_categories] + [
        category for category in available_categories if category not in DEFAULT_CATEGORIES
    ]

    for category in categories:
        category_node = {
            "name": category.title(),
            "points": category_points.get(category, 0),
            "completed_tasks": 0,
            "category": category,
            "children": [],
        }

        root_tags = sorted(
            [tag for tag in tags if tag.get("category") == category and tag.get("parent_tag_id") is None],
            key=lambda item: item["name"],
        )

        for tag in root_tags:
            tag_node = build_tag_node(tag)
            category_node["children"].append(tag_node)
            category_node["completed_tasks"] += tag_node["completed_tasks"]

        root["children"].append(category_node)

    return root


######## Agent-only API surface for Hermes / MCP wrappers

@app.get("/api/agent/tasks", response_model=List[TaskResponse])
async def agent_get_active_tasks(agent: AgentPrincipal = Depends(require_read_agent)):
    """Agent-safe mirror of active task listing."""
    return await get_active_tasks()


@app.get("/api/agent/tasks/remainder", response_model=List[TaskRemainderResponse])
async def agent_get_tasks_with_remainder(
    category: Optional[str] = None,
    agent: AgentPrincipal = Depends(require_read_agent),
):
    """Agent-safe mirror of active tasks with time remaining."""
    return await get_tasks_with_remainder(category=category)


@app.get("/api/agent/tasks/overdue", response_model=List[TaskRemainderResponse])
async def agent_get_overdue_tasks(
    category: Optional[str] = None,
    agent: AgentPrincipal = Depends(require_read_agent),
):
    """Agent-safe overdue task view."""
    return await get_overdue_tasks(category=category)


@app.get("/api/agent/tasks/due-soon", response_model=List[TaskRemainderResponse])
async def agent_get_due_soon_tasks(
    hours: int = Query(DEFAULT_DUE_SOON_HOURS, ge=1, le=168),
    category: Optional[str] = None,
    agent: AgentPrincipal = Depends(require_read_agent),
):
    """Agent-safe near-due task view."""
    return await get_due_soon_tasks(hours=hours, category=category)


@app.post("/api/agent/tasks", response_model=TaskResponse)
async def agent_create_task(
    task: TaskCreate,
    agent: AgentPrincipal = Depends(require_write_agent),
):
    """Agent-safe task creation endpoint."""
    return await create_task(task)


@app.patch("/api/agent/tasks/{task_id}", response_model=TaskResponse)
async def agent_update_task(
    task_id: int,
    task: TaskUpdate,
    agent: AgentPrincipal = Depends(require_write_agent),
):
    """Agent-safe task update endpoint."""
    return await update_task(task_id, task)


@app.post("/api/agent/tasks/{task_id}/complete", response_model=CompletionActionResponse)
async def agent_complete_task(
    task_id: int,
    completion_data: Optional[CompletionData] = None,
    agent: AgentPrincipal = Depends(require_write_agent),
):
    """Agent-safe task completion endpoint."""
    return await complete_task(task_id, completion_data)


@app.get("/api/agent/completed", response_model=List[CompletionResponse])
async def agent_get_completed_tasks(
    limit: int = 50,
    offset: int = 0,
    agent: AgentPrincipal = Depends(require_read_agent),
):
    """Agent-safe completed task history endpoint."""
    return await get_completed_tasks(limit=limit, offset=offset)


@app.patch("/api/agent/completed/{completion_id}")
async def agent_update_completion_notes(
    completion_id: int,
    update: CompletionUpdate,
    agent: AgentPrincipal = Depends(require_write_agent),
):
    """Agent-safe completion note update endpoint."""
    return await update_completion_notes(completion_id, update)


@app.get("/api/agent/summary/domains", response_model=DomainSummaryResponse)
async def agent_get_domain_summary(
    hours: int = Query(DEFAULT_DUE_SOON_HOURS, ge=1, le=168),
    recent_completion_limit: int = Query(10, ge=1, le=50),
    agent: AgentPrincipal = Depends(require_read_agent),
):
    """Agent-safe domain summary endpoint."""
    return await get_domain_summary(hours=hours, recent_completion_limit=recent_completion_limit)


@app.get("/api/agent/summary/maintenance", response_model=MaintenanceSnapshotResponse)
async def agent_get_maintenance_snapshot(
    hours: int = Query(DEFAULT_DUE_SOON_HOURS, ge=1, le=168),
    stale_days: int = Query(DEFAULT_STALE_DAYS, ge=1, le=90),
    recent_completion_limit: int = Query(10, ge=1, le=50),
    agent: AgentPrincipal = Depends(require_read_agent),
):
    """Agent-safe maintenance snapshot endpoint."""
    return await get_maintenance_snapshot(
        hours=hours,
        stale_days=stale_days,
        recent_completion_limit=recent_completion_limit,
    )


@app.get("/api/agent/skill-tree")
async def agent_get_skill_tree(agent: AgentPrincipal = Depends(require_read_agent)):
    """Agent-safe skill tree endpoint."""
    return await get_skill_tree()
