# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from supabase import Client, create_client
from pathlib import Path
from dotenv import load_dotenv
import os
from utils.auth import verify_credentials

# Load in the .env file so you can use your env variables
currdir = Path(__file__).resolve().parent
envpath = currdir / '.env'
load_dotenv(envpath)

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

######## Data definition for the /api/tasks endpoints pertaining to Tasks table
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    priority: int = 3
    due_date: Optional[datetime] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None

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

# Endpoint implementation for our lovely web server API
@app.get("/")
def read_root():
    return {"message": "We WAZ KANGZZZZ!!!!! (Indo-Aryan Edition)"}

@app.get("/api/tasks", response_model=List[TaskResponse])
async def get_active_tasks():
    """
        Retrieve all active tasks
    """
    response = supabase.table('tasks').select("*").eq('is_active', True).execute()
    return response.data

@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(task: TaskCreate):
    """
        Pass in a TaskCreate object
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