from pydantic import BaseModel, field_validator
from typing import Dict, List, Optional
from datetime import datetime
import zoneinfo


######## Data definition for the /api/tasks endpoints pertaining to Tasks table
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    priority: int = 3
    due_date: Optional[datetime] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    assigned_to: Optional[str] = None    # user name (e.g. 'Argus', 'Veltiosi', 'Satyam')
    created_by: Optional[str] = None     # user name of creator

    @field_validator('due_date')
    @classmethod
    def ensure_timezone(cls, v):
        if v and isinstance(v, datetime) and v.tzinfo is None:
            eastern = zoneinfo.ZoneInfo("America/New_York")
            return v.replace(tzinfo=eastern)
        return v

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    category: str
    priority: int
    due_date: Optional[datetime]
    is_recurring: bool
    recurrence_pattern: Optional[str]
    is_active: bool
    created_at: datetime
    needs_completion: Optional[bool] = None
    last_completed: Optional[datetime] = None
    assigned_to: Optional[int] = None
    assigned_to_name: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None

class TaskRemainderResponse(TaskResponse):
    time_remaining: Optional[int] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[datetime] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    is_active: Optional[bool] = None
    assigned_to: Optional[str] = None    # user name to reassign to

    @field_validator('due_date')
    @classmethod
    def ensure_timezone(cls, v):
        if v and isinstance(v, datetime) and v.tzinfo is None:
            eastern = zoneinfo.ZoneInfo("America/New_York")
            return v.replace(tzinfo=eastern)
        return v
    

######## Data definition for the /completed tasks endpoints retrieving all finished tasks

class CompletionData(BaseModel):
    notes: Optional[str] = ""
    quality: Optional[int] = 3

class CompletionResponse(BaseModel):
    id: int
    task_id: int
    task_title: str
    task_category: str
    completed_at: datetime
    notes: Optional[str]
    was_late: bool
    time_spent_minutes: Optional[int]
    points: int

class CompletionUpdate(BaseModel):
    notes: str


class CompletionActionResponse(BaseModel):
    message: str
    task_id: int
    completed_at: datetime
    points_earned: int
    is_recurring: bool
    next_due: Optional[datetime] = None


class DomainSummaryTotals(BaseModel):
    active_tasks: int
    overdue_tasks: int
    due_soon_tasks: int
    recurring_tasks: int
    completed_tasks: int
    total_points: int


class DomainSummaryItem(BaseModel):
    category: str
    active_tasks: int
    overdue_tasks: int
    due_soon_tasks: int
    recurring_tasks: int
    completed_tasks: int
    total_points: int
    last_completed_at: Optional[datetime] = None


class DomainSummaryResponse(BaseModel):
    generated_at: datetime
    due_soon_window_hours: int
    totals: DomainSummaryTotals
    domains: List[DomainSummaryItem]
    recent_completions: List[CompletionResponse]


class MaintenanceSnapshotResponse(BaseModel):
    generated_at: datetime
    due_soon_window_hours: int
    stale_after_days: int
    counts: Dict[str, int]
    active_by_category: Dict[str, int]
    overdue_by_category: Dict[str, int]
    due_soon_by_category: Dict[str, int]
    points_by_category: Dict[str, int]
    overdue_tasks: List[TaskRemainderResponse]
    due_soon_tasks: List[TaskRemainderResponse]
    untagged_active_tasks: List[TaskRemainderResponse]
    stale_active_tasks: List[TaskRemainderResponse]
    recent_completions: List[CompletionResponse]
