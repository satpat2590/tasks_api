# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from supabase import Client, create_client
from pathlib import Path
from dotenv import load_dotenv
import os
from utils.auth import verify_credentials
from utils.data import TaskCreate, TaskResponse, TaskUpdate

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


######## Endpoint implementation for our lovely web server API
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
async def disable_task(task_id: int):
    """
        Soft 'delete' a task by setting is_active to False

        :request: NONE
        :response: Message verifying that task was deactivated successfully
    """
    try:
        response = supabase.table('tasks').update({
            "is_active": False,
            "updated_at": datetime.now().isoformat()
        }).eq('id', task_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Task not found")
            
        return {"message": "Task deactivated successfully"}
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