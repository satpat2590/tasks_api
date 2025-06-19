from pydantic import BaseModel, field_validator
from typing import Optional
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

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[datetime] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    is_active: Optional[bool] = None

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

class CompletionUpdate(BaseModel):
    notes: str