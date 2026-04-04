# ATMA Design Breakdown

## What ATMA Does

ATMA is a personal accountability backend built around tasks, deadlines, completions, tagging, and points. Conceptually, it is a task manager that tries to turn self-improvement into a game:

- tasks are created, updated, completed, and deleted through a FastAPI API
- each task belongs to a growth category such as `mental`, `physical`, `social`, or `financial`
- completions award or deduct points based on priority, recurrence, quality, and lateness
- overdue work can trigger reminder-style notification scripts
- tasks are auto-tagged with Anthropic so they can feed a skill-tree style view
- a skill tree endpoint combines completion history, tag hierarchy, and points into a growth visualization

In short, ATMA is a gamified life-management API with AI-assisted categorization and external accountability hooks.

## High-Level Architecture

The project is split into four main areas:

1. API layer
   - [`main.py`](/Users/satya/tasks_api/main.py) exposes the FastAPI app and all public endpoints.
2. Shared models and helpers
   - [`utils/data.py`](/Users/satya/tasks_api/utils/data.py) defines the request/response schemas.
   - [`utils/tags.py`](/Users/satya/tasks_api/utils/tags.py) manages tag hierarchy traversal and AI-driven auto-tagging.
   - [`utils/auth.py`](/Users/satya/tasks_api/utils/auth.py) contains placeholder HTTP Basic auth logic.
3. Background/accountability scripts
   - [`game_of_life.py`](/Users/satya/tasks_api/game_of_life.py) groups active tasks by urgency and pushes `ntfy.sh` notifications.
   - [`manager.py`](/Users/satya/tasks_api/manager.py) fetches tasks, identifies overdue and near-due items, logs notification state, and applies overdue penalties.
   - [`scripts/game_tracker.py`](/Users/satya/tasks_api/scripts/game_tracker.py) persists point totals and history in a GitHub Gist.
4. Local state and runtime
   - [`data/sent.json`](/Users/satya/tasks_api/data/sent.json) stores which reminders were already sent.
   - [`run.sh`](/Users/satya/tasks_api/run.sh) starts Uvicorn locally.
   - [`requirements.txt`](/Users/satya/tasks_api/requirements.txt) defines Python dependencies.

## Core Domain Model

The system revolves around these logical entities:

- `tasks`
  - active/inactive task records with due dates, recurrence metadata, category, and priority
- `task_completions`
  - completion log with quality, lateness, notes, time spent, and awarded points
- `tags`
  - hierarchical skill/topic taxonomy with parent-child relationships
- `task_tags`
  - many-to-many join table connecting tasks to tags
- `notifications`
  - optional record of sent notifications
- external points ledger
  - a GitHub Gist stores total points, per-category points, deduction markers, and history

The README includes the intended Supabase schema, and the implementation in `main.py` assumes those tables already exist.

## API Responsibilities

[`main.py`](/Users/satya/tasks_api/main.py) is the main product surface.

### Health and listing

- `GET /`
  - simple connectivity check
- `HEAD /`
  - health-check friendly empty response
- `GET /api/tasks`
  - returns active tasks only
- `GET /api/tasks/remainder`
  - returns active tasks plus computed `time_remaining` in integer hours

### Task lifecycle

- `POST /api/tasks`
  - inserts a task into Supabase
  - immediately calls Anthropic-based auto-tagging
  - ensures any missing hierarchical tags exist
  - inserts rows into `task_tags`
- `PATCH /api/tasks/{task_id}`
  - partial update of mutable fields
- `PATCH /api/tasks/disable/{task_id}`
  - actually functions as "complete task"
  - logs a completion row
  - computes point impact
  - deactivates non-recurring tasks
  - advances the due date for recurring tasks
- `DELETE /api/tasks/{task_id}`
  - deletes dependent rows and then hard-deletes the task

### Completion history

- `GET /api/completed`
  - returns recent completion records joined to task title/category
- `PATCH /api/completed/{completion_id}`
  - updates notes on a completion record

### Skill visualization

- `GET /api/skill-tree`
  - loads all tags
  - loads all completions
  - derives tag completion counts
  - loads points from GitHub Gist
  - returns a nested category/tag tree suitable for a frontend visualization

## Main Runtime Flows

### 1. Task creation flow

1. Client submits a new task to `POST /api/tasks`.
2. FastAPI validates the payload with `TaskCreate`.
3. The task is inserted into Supabase.
4. `auto_tag_task()` loads existing tags in that category.
5. Anthropic is prompted to suggest tag paths.
6. Each returned path is normalized into actual tag rows by `ensure_tag_exists()`.
7. Leaf tags are connected to the task through `task_tags`.

This makes task creation the main AI-enhanced workflow in the system.

### 2. Task completion flow

1. Client calls `PATCH /api/tasks/disable/{task_id}`.
2. The task is loaded from Supabase.
3. Completion metadata is prepared, including quality and notes.
4. Lateness is computed from the due date.
5. Points are calculated from:
   - task priority
   - recurrence pattern
   - completion quality
   - lateness
6. A row is inserted into `task_completions`.
7. The task is either deactivated or advanced to the next due date if recurring.

This endpoint is the core game mechanic because it turns action into score changes.

### 3. Accountability/notification flow

There are two overlapping accountability scripts:

- [`game_of_life.py`](/Users/satya/tasks_api/game_of_life.py)
  - fetches `/api/tasks/remainder`
  - groups tasks into `OVERDUE`, `IMMEDIATE`, `URGENT`, `SOON`, and `LATER`
  - sends grouped messages to `ntfy.sh`
- [`manager.py`](/Users/satya/tasks_api/manager.py)
  - fetches `/api/tasks`
  - identifies overdue and under-3-hour tasks
  - suppresses duplicate sends using [`data/sent.json`](/Users/satya/tasks_api/data/sent.json)
  - prepares reminder messages
  - applies overdue penalties using the GitHub Gist points system

Together, these scripts show the project’s intent: the backend is not just a CRUD API, it is meant to pressure the user into staying on track.

### 4. Skill tree generation flow

1. Load all tags from Supabase.
2. Load points totals from GitHub Gist.
3. Load completion records from `task_completions`.
4. For each completed task, load its tags and derive tag paths.
5. Aggregate completion counts by tag path.
6. Build a nested tree under four root life categories.

The output is designed for a frontend that wants to visualize growth as a tree of skills and subskills.

## External Integrations

ATMA depends on several outside systems:

- Supabase
  - primary persistence layer for tasks, tags, completions, and join tables
- Anthropic
  - used during task creation for automatic tag suggestion
- GitHub Gist
  - used as a lightweight external datastore for points and history
- `ntfy.sh`
  - used for push-style notification delivery
- Render
  - referenced as a hosted API target in scripts
- Twitter/X
  - present as a future or experimental notification channel in [`scripts/tweeter.py`](/Users/satya/tasks_api/scripts/tweeter.py)

## Design Characteristics

### What is strong about the design

- The project has a clear product idea.
  - Everything points toward one coherent goal: behavior change through accountability.
- The API surface is compact and easy to reason about.
- Pydantic models give the task and completion payloads a clean contract.
- The tag hierarchy design supports richer analytics than flat labels.
- The skill tree endpoint is a nice bridge from raw task data to user-facing progression.
- The reminder scripts are small and understandable, which makes experimentation easy.

### What the design implicitly assumes

- Supabase is always reachable and already provisioned with the expected schema.
- Environment variables are present before the app imports and initializes clients.
- AI tagging is reliable enough to sit directly inside synchronous task creation.
- A GitHub Gist is acceptable as the source of truth for points.
- One-user or low-concurrency operation is the primary use case.

## Findings and Risks

These are the most important implementation findings from the code review.

### 1. Environment loading is incomplete

[`main.py`](/Users/satya/tasks_api/main.py) imports `load_dotenv` but never calls it before building the Supabase client. If env vars are not injected by the shell/runtime, startup will fail or initialize with `None`.

### 2. Auth is effectively not in use

[`utils/auth.py`](/Users/satya/tasks_api/utils/auth.py) contains placeholder credentials, but the FastAPI routes do not use `Depends(verify_credentials)`. The API is effectively open unless protected elsewhere by infrastructure.

### 3. Task creation is tightly coupled to Anthropic availability

`POST /api/tasks` inserts the task and then immediately calls `auto_tag_task()`. If Anthropic errors, returns malformed output, or env config is missing, task creation can fail after partial work or behave inconsistently.

### 4. Points are computed in two different places

[`main.py`](/Users/satya/tasks_api/main.py) calculates completion points inside the completion endpoint, while [`scripts/game_tracker.py`](/Users/satya/tasks_api/scripts/game_tracker.py) also contains point logic. This creates drift risk as rules evolve.

### 5. Gist-backed points are separate from completion-backed points

Completion rows store `points`, but the skill tree reads total points from GitHub Gist, not by aggregating `task_completions`. That means the system has two score sources and they can diverge.

### 6. Background scripts target hosted URLs, not local config

[`game_of_life.py`](/Users/satya/tasks_api/game_of_life.py) and [`manager.py`](/Users/satya/tasks_api/manager.py) point at a hard-coded Render URL. That makes local development and environment portability weaker.

### 7. `manager.py` notification sending is partly stubbed

The notification loop prints `POSTING:` messages, but the Twitter/X send is commented out. So the script’s effective behavior is mixed: dedupe and penalty logic work, but one delivery path is unfinished.

### 8. Several imports and files look unfinished or unused

- [`alert.py`](/Users/satya/tasks_api/alert.py) is empty
- `load_dotenv`, `Path`, `verify_credentials`, `build_hierarchy_string`, `ensure_tag_exists`, `get_tag_by_id`, `calculate_points`, and `Anthropic` are imported in [`main.py`](/Users/satya/tasks_api/main.py) but not all are used there
- [`scripts/requirements.txt`](/Users/satya/tasks_api/scripts/requirements.txt) is empty
- [`render_run.sh`](/Users/satya/tasks_api/render_run.sh) refers to `requirement.txt` instead of `requirements.txt`

These are signs the project is still evolving and not fully tightened.

### 9. Completion timing semantics are a bit muddy

In the completion flow, `time_spent_minutes` is derived from how late the task is relative to due date, not from actual work duration. That field currently behaves more like "minutes overdue after deadline" than "time spent on task".

### 10. Skill tree generation may become expensive

`GET /api/skill-tree` performs repeated lookup patterns:

- load all completions
- for each completion, query task tags
- for each tag path, traverse hierarchy by repeated DB lookups

This is acceptable at small scale, but it will get expensive as data grows.

## Practical Summary

ATMA is a FastAPI + Supabase backend for a highly personal, gamified task system. Its real product idea is not generic productivity; it is accountability-driven self-development. The task model, AI auto-tagging, points, recurring completion logic, notification scripts, and skill tree all support that single goal.

The codebase is functional and conceptually coherent, but it is still in a prototype-to-early-product stage. The main opportunities for hardening are configuration loading, authentication, points consistency, error handling around AI tagging, and clearer separation between core API behavior and background/accountability side systems.
