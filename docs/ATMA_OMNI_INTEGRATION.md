# ATMA Omni Integration Plan

## Scope

This document defines how to evolve Atma into an LLM-friendly, MCP-friendly task domain service that remains cloud-hosted on Render and backed by Supabase.

It is intentionally scoped to **Atma only**.

- Omni logic will continue to live on the ASUS laptop.
- Hermes and other local agents/services will continue to run on the ASUS laptop.
- This Mac Mini is the development environment for Atma.
- Atma will remain the cloud-hosted task and progress service within the broader Omni system.

## Current Deployment Context

### Existing reality

- Atma backend is deployed on Render.
- Atma stores task and metadata records in Supabase.
- Hermes and the rest of the Omni-side agent stack live on the ASUS laptop.
- Omni is not yet part of this repository and should not be implemented here.

### Updated assumptions

- The old `manager.py` and `game_of_life.py` maintenance pattern should be retired.
- The GitHub Gist points ledger is no longer needed.
- Points are now tracked directly in Supabase and Atma should treat Supabase as the sole source of truth.

## Goal

Turn Atma into a **stable cloud task domain service** that an LLM agent can safely operate through structured tools.

In practice, this means:

- Hermes can create, update, complete, and inspect tasks through deterministic Atma interfaces.
- Hermes can retrieve summaries like active tasks, overdue tasks, due-soon tasks, and points by domain.
- Atma remains the canonical source of truth for task state, recurrence, points, and domain rollups.
- Omni can later consume Atma as one domain node without needing Atma to embed Omni-specific orchestration logic.

## Non-Goals

These items are explicitly out of scope for this document and this repo for now:

- implementing Omni orchestration logic on the Mac Mini
- moving Hermes off the ASUS laptop
- giving the LLM direct database access
- embedding Edoras logic into Atma
- rebuilding Atma into a monolith for all Omni domains

## Target System Shape

Atma should become a clean three-layer service:

1. Domain API Layer
   - FastAPI endpoints for tasks, completions, summaries, and maintenance operations
2. Domain Logic Layer
   - deterministic rules for recurrence, due-state classification, points, and rollups
3. Agent Tool Surface
   - MCP-friendly or tool-friendly interfaces that Hermes can call from the ASUS laptop

The key design rule is:

**the LLM decides actions, but Atma decides truth**

That means Hermes can say:

- "create a daily task in physical"
- "show my overdue tasks"
- "complete this task with good quality"
- "summarize points by domain"

But Atma should still be responsible for:

- validating allowed categories
- computing due windows
- computing recurring next dates
- calculating points
- deriving domain summaries
- recording audit history

## Deployment Topology

### Node 1: Atma cloud service

- hosted on Render
- backed by Supabase
- exposes HTTPS API
- exposes an MCP-friendly tool surface, either directly or via a thin adapter

### Node 2: Omni local control plane

- runs on ASUS laptop
- contains Hermes and future Omni orchestration logic
- calls Atma over authenticated HTTPS
- consumes Atma summaries and task operations as a remote domain service

This keeps the separation you wanted:

- Atma is the cloud task engine
- Omni is the local orchestration layer

## Architectural Direction

### Atma as a domain service

Atma should own:

- tasks
- task completions
- tags and tag hierarchy
- points and points history
- recurrence rules
- overdue / due-soon classification
- domain and skill-tree rollups
- action audit logs

### Hermes as an operator

Hermes should own:

- natural language interpretation
- choosing which Atma tool to call
- asking for clarification when instructions are ambiguous
- proposing new tasks or restructures
- producing human-readable summaries from Atma state

Hermes should not own:

- points math
- canonical recurrence logic
- direct DB writes
- database joins and rollups
- the definition of active/overdue/due-soon truth

## Why The Old Pattern Should Be Retired

The previous design used local maintenance scripts like:

- [`manager.py`](/Users/satya/tasks_api/manager.py)
- [`game_of_life.py`](/Users/satya/tasks_api/game_of_life.py)

Those scripts were useful during prototyping, but they are not ideal for a long-term LLM-integrated system because:

- business logic is split across API code and scripts
- notifications and penalties are hard-coded outside the core service
- scripts are environment-bound and harder to reason about remotely
- agent-driven maintenance needs structured state and deterministic endpoints, not sidecar logic

The replacement model should be:

- Atma exposes structured state and controlled actions
- Hermes consumes those actions and decides what to do
- any scheduled maintenance becomes a lightweight trigger that asks Hermes to review state, not a script that holds business truth

## MCP-Friendly Direction

Atma does not need to run Omni inside itself. It only needs to be easy for Hermes to use as a remote tool system.

There are two valid ways to do this:

### Option A: Keep Atma as an HTTPS API and add a thin MCP adapter on the ASUS laptop

This is likely the best first step.

- Atma stays as a standard FastAPI service on Render
- Hermes talks to a local MCP server on the ASUS laptop
- that MCP server simply wraps Atma HTTP endpoints into structured tools

Benefits:

- minimal disruption to Atma deployment
- no need to embed MCP transport into the Render app immediately
- easier to evolve tool contracts locally while Atma API stabilizes

### Option B: Expose MCP-native endpoints from Atma later

This can come later if it becomes valuable.

- Atma could expose a remote MCP server directly
- Hermes could call it over the network without a local wrapper

Benefits:

- fewer moving pieces long-term
- cleaner service boundary once contracts are stable

Recommendation:

Start with **Option A** and design Atma endpoints as if they will be wrapped into MCP tools. That gets you MCP friendliness without forcing Atma to become an MCP server immediately.

## Required Atma Capabilities

Atma should expose enough structured functionality that Hermes never has to infer core state by scraping raw records.

### Task operations

- create a task
- update a task
- complete a task
- deactivate/archive a task
- reschedule or snooze a task
- fetch one task by id
- list active tasks
- list tasks by domain
- list recurring tasks

### Deadline-oriented views

- list overdue tasks
- list tasks due within `N` hours
- list tasks due today
- list tasks with no due date
- list stale tasks that have not been touched recently

### Progress and scoring views

- summarize points by high-level domain
- summarize points by tag path
- summarize recent completions
- summarize recurring compliance or streaks
- return skill tree data

### Maintenance views

- return a compact system snapshot for Hermes
- return duplicate or near-duplicate tasks
- return tasks with weak or missing tags
- return tasks needing clarification

## Proposed MCP Tool Surface

Whether implemented directly or through a wrapper, Atma should eventually expose tools shaped roughly like this:

- `atma.list_active_tasks(category?, limit?)`
- `atma.list_due_tasks(within_hours?, category?)`
- `atma.list_overdue_tasks(category?)`
- `atma.get_task(task_id)`
- `atma.create_task(title, description?, category, due_date?, is_recurring?, recurrence_pattern?, tags?)`
- `atma.update_task(task_id, fields)`
- `atma.complete_task(task_id, quality?, notes?)`
- `atma.reschedule_task(task_id, due_date, reason?)`
- `atma.snooze_task(task_id, duration, reason?)`
- `atma.archive_task(task_id, reason?)`
- `atma.get_domain_points_summary()`
- `atma.get_tag_points_summary(category?)`
- `atma.get_skill_tree(category?)`
- `atma.get_maintenance_snapshot()`
- `atma.search_tasks(query, filters?)`

Each tool should:

- be deterministic
- return machine-friendly JSON
- support validation errors cleanly
- avoid requiring Hermes to assemble complex joins itself

## Atma API Changes Recommended

The current API is a good starting point, but it needs some cleanup and expansion.

### Keep and refine

- `GET /api/tasks`
- `POST /api/tasks`
- `PATCH /api/tasks/{task_id}`
- `GET /api/completed`
- `GET /api/skill-tree`

### Replace or rename

- replace `PATCH /api/tasks/disable/{task_id}` with a clearer completion endpoint

Recommended replacement:

- `POST /api/tasks/{task_id}/complete`

Optional supporting endpoints:

- `POST /api/tasks/{task_id}/archive`
- `POST /api/tasks/{task_id}/reschedule`
- `POST /api/tasks/{task_id}/snooze`

### Add summary endpoints

- `GET /api/summary/domains`
  - active tasks, overdue tasks, due-soon counts, points, recent completions by domain
- `GET /api/summary/today`
  - today-specific operational view for Hermes
- `GET /api/summary/maintenance`
  - compact LLM-friendly snapshot
- `GET /api/tasks/overdue`
  - explicit overdue view
- `GET /api/tasks/due-soon?hours=24`
  - explicit near-due view

### Add explainability endpoints

Useful for agent behavior and debugging:

- `GET /api/tasks/{task_id}/explain`
  - why the task is in its current state, due status, recurrence info, points implications

## Data Model Direction

Since points are now in Supabase, the database should be treated as canonical.

### Canonical entities

- `tasks`
- `task_completions`
- `tags`
- `task_tags`
- `notifications` if still desired
- `point_events`
- `agent_actions`

### Recommended additions

#### `point_events`

Purpose:

- canonical history of all positive and negative point changes

Suggested fields:

- `id`
- `task_id` nullable
- `completion_id` nullable
- `domain`
- `tag_path` nullable
- `event_type`
- `points_delta`
- `reason`
- `created_at`
- `created_by`

This gives you a clean ledger for:

- task completions
- overdue penalties
- bonuses
- manual adjustments

#### `agent_actions`

Purpose:

- audit trail of Hermes or other system activity

Suggested fields:

- `id`
- `agent_name`
- `action_type`
- `target_type`
- `target_id`
- `request_payload`
- `result_payload`
- `approval_mode`
- `status`
- `created_at`

This makes LLM-driven maintenance safe and reviewable.

#### Optional task metadata fields

Potentially useful additions to `tasks`:

- `source`
  - `human`, `hermes`, `import`, etc.
- `created_by_agent`
- `last_reviewed_at`
- `last_reviewed_by`
- `clarity_score` or `needs_clarification`
- `maintenance_state`

These are helpful once agents start maintaining the backlog.

## Business Logic Consolidation

Atma should centralize all deterministic maintenance logic inside the service.

### Logic that should live inside Atma

- recurrence calculation
- due-state classification
- late completion handling
- points award and penalty calculation
- tag rollup and domain rollup
- duplicate detection heuristics
- consistency checks

### Logic that should not remain in standalone scripts

- primary overdue classification
- points deductions
- source-of-truth reminder decisions
- long-term state mutation

If you still want scheduled behavior, it should call Atma endpoints or Hermes tools rather than owning logic directly.

## New Maintenance Model

The goal is not "no scheduling at all." The goal is "no fragile cron jobs holding business logic."

The recommended model is:

1. a lightweight trigger runs on a schedule somewhere convenient
2. Hermes requests `atma.get_maintenance_snapshot()`
3. Hermes decides what action, if any, should be taken
4. Hermes calls Atma tools for approved actions
5. Atma records those actions and applies deterministic rules

This gives you a smarter maintenance loop without scattering truth across scripts.

Examples:

- Hermes notices several overdue `physical` tasks and suggests consolidation
- Hermes notices a recurring task has gone stale and proposes rescheduling
- Hermes notices a domain has low recent activity and recommends new tasks

## Security Model

Atma should not trust arbitrary callers once it becomes an agent-operated cloud service.

Recommended approach:

- use service-level API auth for Hermes and trusted clients
- issue a dedicated Hermes token
- keep user-facing auth separate from agent auth
- log all agent actions
- support read-only vs write scopes if needed later

Minimum requirement:

- replace placeholder auth with a real token-based mechanism before giving Hermes write access

## Error Handling Expectations

Agent-facing systems need very clear, structured failures.

Atma endpoints and tools should return:

- validation errors
- missing task errors
- duplicate task warnings
- recurrence parsing errors
- authorization failures
- partial-success warnings where relevant

This is important because Hermes will need machine-readable outcomes, not vague exceptions.

## Suggested Phased Implementation

### Phase 1: Clean service boundaries

- remove dependence on `manager.py` and `game_of_life.py`
- fully remove Gist-based points logic from the runtime path
- ensure points are Supabase-backed only
- clean up task completion and recurrence logic in the API
- introduce proper auth

### Phase 2: Add agent-friendly summary endpoints

- add domain points summary endpoint
- add due-soon and overdue endpoints
- add maintenance snapshot endpoint
- add clearer task completion/reschedule/archive endpoints

### Phase 3: Add auditability and ledger support

- add `point_events`
- add `agent_actions`
- record all Hermes write operations

### Phase 4: Add MCP wrapper on ASUS laptop

- build a thin local wrapper that converts Hermes tool calls into Atma API calls
- keep Omni logic outside Atma
- test end-to-end natural language flows through Hermes

### Phase 5: Tighten maintenance behavior

- replace ad hoc scheduled scripts with a single maintenance review workflow
- decide which actions Hermes may perform automatically
- leave high-impact actions behind explicit approval if desired

## Example End-State Workflows

### Create a recurring task

User says:

"Create a daily task to review posture exercises in physical."

Flow:

1. Hermes parses intent
2. Hermes calls `atma.create_task(...)`
3. Atma validates category and recurrence
4. Atma stores the task
5. Atma applies tag logic
6. Atma returns the created task record
7. Atma logs the agent action

### Get domain score breakdown

User says:

"How are my points looking across domains?"

Flow:

1. Hermes calls `atma.get_domain_points_summary()`
2. Atma aggregates data from Supabase
3. Hermes formats a natural language answer

### Maintain stale tasks

Scheduled review happens:

1. Hermes calls `atma.get_maintenance_snapshot()`
2. Atma returns overdue counts, stale tasks, due-soon tasks, low-activity domains, and other structured signals
3. Hermes decides whether to suggest cleanup, create follow-up tasks, or reschedule items
4. Hermes calls Atma write tools as appropriate

## Recommended First Build Targets

If the goal is to make progress quickly, these are the best first implementation targets in Atma:

1. make Supabase the only points source everywhere
2. replace `disable` with `complete`
3. add `GET /api/summary/domains`
4. add `GET /api/tasks/overdue`
5. add `GET /api/tasks/due-soon`
6. add `GET /api/summary/maintenance`
7. add token-based auth for Hermes
8. add `agent_actions` logging

## Final Position

Atma should remain a separate cloud-hosted domain service. That separation is a strength.

The right future is not to collapse Atma into Omni, but to make Atma:

- deterministic
- well-instrumented
- agent-friendly
- MCP-friendly
- easy for Hermes to consume remotely

With that setup:

- the ASUS laptop remains the Omni control plane
- Hermes remains the local operator
- Atma remains the remote task and growth engine on Render
- Supabase remains the source of truth

That architecture preserves clean boundaries while still allowing LLM-driven maintenance and natural language control.
