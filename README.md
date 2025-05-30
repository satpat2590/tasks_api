# tasks_api
FastAPI project which will interface with Supabase to perform CRUD operations on a database which consists of various Tasks + other metadata


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