# tasks_api

A gamified task management system built with FastAPI and Supabase, designed to drive experiential growth and personal accountability.

## Project Overview

`tasks_api` is the backend for a comprehensive personal growth platform. It transforms standard task management into a game-like experience where users earn points for completing tasks and face "punishments" or aggressive notifications for falling behind.

### Key Features

- **Gamified Task Tracking**: Earn points based on task priority, recurrence, and completion quality.
- **Skill Tree**: A hierarchical visualization of growth across mental, physical, social, and financial domains.
- **AI-Powered Auto-Tagging**: Leverages the Anthropic API to automatically categorize and tag tasks into a complex hierarchy.
- **Accountability System**: Monitors overdue tasks and triggers reminders or penalty-based notifications (e.g., via Twitter).
- **Supabase Integration**: Robust data storage and real-time capabilities.
- **Game of Life accountability script**: Periodically fetches active tasks and groups them based on the time remaining to send periodic aggressive notifications to notify you of your pending tasks.
- **FastAPI Core**: High-performance, asynchronous REST API.

### Technology Stack

- **Framework**: FastAPI
- **Database/Auth**: Supabase (PostgreSQL)
- **AI/LLM**: Anthropic Claude API (for auto-tagging)
- **Monitoring**: Integration with external services (e.g., OnRender, Twitter/X for notifications)

---


# Description

I need to hold myself accountable for my life and to strive for experiential growth. To do so, I will create a task manager which will be able to store and modify tasks, as well as an Accountability System which will help me stay on track with the growth I envision. 

# Run Methodology

It's as simple as: 
```bash
./run.sh 
```

This will simply run the uvicorn web server on post 3000 locally. You can use http://localhost:3000 to test the endpoints using something like Postman or any client. 

<b>Note that currently, we don't have the ability to host the API on a dedicated server, so calls from servers external to local network will FAIL.</b>


# Technical Layout

TBA!

## Endpoints (as of 05/31/2025)

GET /

 - The main endpoint to return any regular data which will verify that you are connected to the API. 
 - There will be authentication which is required prior to clients being able to connect to the API, so this endpoint will be called once auth is verified. 

GET /api/tasks

 - This endpoint will return a JSON separated list of tasks with all of their columns present.  

```python
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
```

POST /api/tasks 

 - This endpoint will allow you to send a JSON body containing various field names which will then get validated by backend and then formatted into an INSERT query inside the database. 
 - Simply pass in a JSON object using the data definition below. 

```python
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    priority: int = 3
    due_date: Optional[datetime] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
```

PATCH /api/tasks/{task_id}

 - You can edit your tasks using this endpoint. 
 - Simply pass in a JSON object using the data definition below. 

```python
class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[datetime] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    is_active: Optional[bool] = None
```

GET /api/tasks/remainder

 - This endpoint will return a JSON list of active tasks with an additional `time_remaining` field (integer hours).
 - Useful for grouping and sorting tasks by urgency.

PATCH /api/tasks/disable/{task_id}

 - 

DELETE /api/tasks/{task_id}

 - 


# Supabase database layout 

-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.notifications (
  id integer NOT NULL DEFAULT nextval('notifications_id_seq'::regclass),
  task_id integer,
  sent_at timestamp with time zone DEFAULT now(),
  notification_type character varying CHECK (notification_type::text = ANY (ARRAY['reminder'::character varying, 'overdue'::character varying, 'punishment'::character varying, 'summary'::character varying]::text[])),
  channel character varying CHECK (channel::text = ANY (ARRAY['email'::character varying, 'sms'::character varying, 'both'::character varying]::text[])),
  CONSTRAINT notifications_pkey PRIMARY KEY (id),
  CONSTRAINT notifications_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id)
);
CREATE TABLE public.punishment_rules (
  id integer NOT NULL DEFAULT nextval('punishment_rules_id_seq'::regclass),
  hours_overdue integer NOT NULL UNIQUE,
  action character varying NOT NULL,
  is_active boolean DEFAULT true,
  CONSTRAINT punishment_rules_pkey PRIMARY KEY (id)
);
CREATE TABLE public.tags (
  id integer NOT NULL DEFAULT nextval('tags_id_seq'::regclass),
  name character varying NOT NULL,
  parent_tag_id integer,
  category character varying NOT NULL,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT tags_pkey PRIMARY KEY (id),
  CONSTRAINT tags_parent_tag_id_fkey FOREIGN KEY (parent_tag_id) REFERENCES public.tags(id)
);
CREATE TABLE public.task_completions (
  id integer NOT NULL DEFAULT nextval('task_completions_id_seq'::regclass),
  task_id integer,
  completed_at timestamp with time zone DEFAULT now(),
  completion_quality integer CHECK (completion_quality >= 1 AND completion_quality <= 5),
  notes text,
  was_late boolean DEFAULT false,
  time_spent_minutes integer,
  points smallint DEFAULT '0'::smallint,
  CONSTRAINT task_completions_pkey PRIMARY KEY (id),
  CONSTRAINT task_completions_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id)
);
CREATE TABLE public.task_tags (
  task_id integer NOT NULL,
  tag_id integer NOT NULL,
  CONSTRAINT task_tags_pkey PRIMARY KEY (task_id, tag_id),
  CONSTRAINT task_tags_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id),
  CONSTRAINT task_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tags(id)
);
CREATE TABLE public.tasks (
  id integer NOT NULL DEFAULT nextval('tasks_id_seq'::regclass),
  title character varying NOT NULL,
  description text,
  category character varying CHECK (category::text = ANY (ARRAY['physical'::character varying, 'mental'::character varying, 'social'::character varying, 'financial'::character varying]::text[])),
  priority integer DEFAULT 3 CHECK (priority >= 1 AND priority <= 5),
  due_date timestamp with time zone,
  is_recurring boolean DEFAULT false,
  recurrence_pattern character varying,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  chain_group character varying,
  CONSTRAINT tasks_pkey PRIMARY KEY (id)
);

Side notes: 

- Supabase uses method chaining, not SQL strings
- .execute() runs the query
- Response is in response.data
- Dates need .isoformat() for JSON serialization
- Supabase returns the inserted row automatically


# Game of Life

The `game_of_life.py` script serves as the primary accountability driver. It:
1. Connects to `/api/tasks/remainder` to fetch tasks with relative time.
2. Groups tasks into urgency buckets:
   - **OVERDUE**: Tasks past their due date.
   - **IMMEDIATE**: Less than 3 hours remaining.
   - **URGENT**: Less than 12 hours remaining.
   - **SOON**: Less than 24 hours remaining.
   - **LATER**: Everything else.
3. Sends notifications for each group via **ntfy.sh** to a dedicated channel.