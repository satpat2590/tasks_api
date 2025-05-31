# tasks_api
FastAPI project which will interface with Supabase to perform CRUD operations on a database which consists of various Tasks + other metadata


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

PATCH /api/tasks/disable/{task_id}

 - 

DELETE /api/tasks/{task_id}

 - 


# Supabase database layout 

-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.
```sql
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

CREATE TABLE public.task_completions (
  id integer NOT NULL DEFAULT nextval('task_completions_id_seq'::regclass),
  task_id integer,
  completed_at timestamp with time zone DEFAULT now(),
  completion_quality integer CHECK (completion_quality >= 1 AND completion_quality <= 5),
  notes text,
  was_late boolean DEFAULT false,
  CONSTRAINT task_completions_pkey PRIMARY KEY (id),
  CONSTRAINT task_completions_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id)
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
  CONSTRAINT tasks_pkey PRIMARY KEY (id)
);
```

Side notes: 

- Supabase uses method chaining, not SQL strings
- .execute() runs the query
- Response is in response.data
- Dates need .isoformat() for JSON serialization
- Supabase returns the inserted row automatically


