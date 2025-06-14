# main.py
import os, re
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import zoneinfo
from supabase import Client, create_client
from pathlib import Path
from dotenv import load_dotenv
from utils.auth import verify_credentials
from utils.data import TaskCreate, TaskResponse, TaskUpdate, CompletionData, CompletionResponse, CompletionUpdate
from scripts.game_tracker import get_points, save_points, calculate_points

# Load in the .env file so you can use your env variables
#currdir = Path(__file__).resolve().parent
#envpath = currdir / '.env'

# Set up the FastAPI backend. Use uvicorn as your web server (preferably).
app = FastAPI()

# Make the connection to Supabase instance
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# CORS for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sbpatel.dev", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


######## Endpoint implementation for our lovely web server API ###########
@app.get("/")
def read_root():
    return {"message": "We WAZ KANGZZZZ!!!!! (Indo-Aryan Edition)"}

@app.head("/")
async def head_root():
    """
    Handles HEAD requests for the root path.
    This is often used for health checks.
    """
    return  # Returning nothing (or an empty string) is sufficient for HEAD


####################### /api/tasks
@app.get("/api/tasks", response_model=List[TaskResponse])
async def get_active_tasks():
    """
        Retrieve all active tasks

        :request: NONE
        :response: A list of TaskResponse objects
    """
    response = supabase.table('tasks').select("*").eq('is_active', True).execute()
    return JSONResponse(
        content=response.data,
        media_type="application/json",
        headers={"Content-Type": "application/json; charset=utf-8"}
    )

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
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task: TaskUpdate):
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


@app.patch("/api/tasks/disable/{task_id}")
async def disable_task(task_id: int, completion_data: Optional[dict] = None):
    """
    Complete task - log completion and handle recurring tasks
    
    Optional body:
    {
        "quality": 1-5,
        "notes": "string"
    }
    """
    try:
     # Get the task first
        task = supabase.table('tasks').select("*").eq('id', task_id).execute()
        if not task.data:
            raise HTTPException(status_code=404, detail="Task not found")
        
        task_data = task.data[0]
        
###### Log the completion in the task_completion table
        completion_record = {
            "task_id": task_id,
            "completion_quality": completion_data.get("quality", 3) if completion_data else 3,
            "notes": completion_data.get("notes", "") if completion_data else "",
            "was_late": False  # Calculate if needed based on due_date
        }
        
     # Check if task was completed late
        if task_data['due_date']:
            due = datetime.fromisoformat(task_data['due_date'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > due:
                completion_record["was_late"] = True
     
     # Insert the completed task into the task_completion table
        supabase.table('task_completions').insert(completion_record).execute()
        
###### Award points
        points_data = get_points()
        base_points = task_data['priority'] * 10
        
     # Apply recurring point deduction
        if task_data['is_recurring'] and 'daily' in task_data.get('recurrence_pattern', '').lower():
            base_points = int(base_points * 0.3)
        
     # Apply quality bonus/penalty
        quality = completion_record["completion_quality"]
        if quality >= 4:
            base_points = int(base_points * 1.2)  # 20% bonus
        elif quality <= 2:
            base_points = int(base_points * 0.8)  # 20% penalty
        
     # Update points
        points_data['total'] += base_points
        points_data['categories'][task_data['category']] += base_points
        points_data['history'].append({
            "task_id": task_id,
            "task": task_data['title'],
            "category": task_data['category'],
            "points": base_points,
            "type": "completed",
            "quality": quality,
            "date": datetime.now(timezone.utc).isoformat()
        })
     
        save_points(points_data)
        
###### Set the task in the table to inactive / update due date if recurrent

     # Handle recurring vs non-recurring
        if not task_data['is_recurring']:
            response = supabase.table('tasks').update({
                "is_active": False
            }).eq('id', task_id).execute()
            return {"message": f"Task completed! +{base_points} points", "points_earned": base_points}
        
     # If recurring, calculate next due date (existing logic)
        current_due = datetime.fromisoformat(task_data['due_date'].replace('Z', '+00:00'))
        pattern = task_data['recurrence_pattern'].lower()
        
     # Calculate next occurrence
        if pattern == 'daily':
            next_due = current_due + timedelta(days=1)
        elif pattern == 'weekly':
            next_due = current_due + timedelta(weeks=1)
        elif pattern == 'monthly':
            if current_due.month == 12:
                next_due = current_due.replace(year=current_due.year + 1, month=1)
            else:
                next_due = current_due.replace(month=current_due.month + 1)
        elif pattern == 'yearly':
            next_due = current_due.replace(year=current_due.year + 1)
        else:
         # Try to parse custom patterns like "every 3 days"
            match = re.match(r'every (\d+) days?', pattern)
            if match:
                days = int(match.group(1))
                next_due = current_due + timedelta(days=days)
            else:
                next_due = current_due + timedelta(weeks=1)
        
     # Update the due date
        response = supabase.table('tasks').update({
            "due_date": next_due.isoformat()
        }).eq('id', task_id).execute()
        
        return {
            "message": f"Recurring task completed! +{base_points} points. Next due: {next_due.date()}", 
            "points_earned": base_points,
            "next_due": next_due.isoformat()
        }
        
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

     # Finally, delete the task
        supabase.table('tasks').delete().eq('id', task_id).execute()

        return {"message": "Task and all related records permanently deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

####################### /api/completed

@app.get("/api/completed", response_model=List[CompletionResponse])
async def get_completed_tasks(limit: int = 50, offset: int = 0):
    """Get completed tasks with task details"""
    response = supabase.table('task_completions').select(
        "*, tasks(title, category)"
    ).order('completed_at', desc=True).range(offset, offset + limit - 1).execute()
    
    # Transform the response
    completions = []
    for item in response.data:
        completions.append({
            "id": item['id'],
            "task_id": item['task_id'],
            "task_title": item['tasks']['title'],
            "task_category": item['tasks']['category'],
            "completed_at": item['completed_at'],
            "notes": item['notes'],
            "was_late": item['was_late']
        })
    
    return completions

@app.patch("/api/completed/{completion_id}")
async def update_completion_notes(completion_id: int, update: CompletionUpdate):
    """Update notes for a completed task"""
    response = supabase.table('task_completions').update({
        "notes": update.notes
    }).eq('id', completion_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Completion not found")
    
    return {"message": "Notes updated"}