# ATMA Agent Endpoints

## Purpose

This document describes the Atma endpoints intended for Hermes and other agentic callers.

These endpoints:

- live under `/api/agent/*`
- require bearer-token agent auth
- are designed for MCP wrappers and tool calling
- leave the existing public/frontend routes unchanged

This split lets the production website continue using the current public API while Hermes and future agents use a dedicated protected surface.

## Auth

All `/api/agent/*` endpoints require:

```http
Authorization: Bearer <agent-token>
```

Atma validates the token against one of:

- `ATMA_HERMES_TOKEN`
- `ATMA_AGENT_TOKEN`
- `ATMA_READONLY_AGENT_TOKEN`
- `ATMA_AGENT_TOKENS_JSON`

Scopes:

- `read`
  - inspect state and summaries
- `write`
  - create, update, complete, or otherwise mutate task data

`write` tokens implicitly also have `read`.

## Endpoint Summary

### Identity

#### `GET /api/agent/me`

Purpose:

- confirms which agent identity and scopes the current bearer token resolves to

Response:

```json
{
  "agent": "hermes",
  "scopes": ["read", "write"]
}
```

### Task Read Views

#### `GET /api/agent/tasks`

Purpose:

- list active tasks

Scope:

- `read`

#### `GET /api/agent/tasks/remainder`

Purpose:

- list active tasks with computed `time_remaining`

Query params:

- `category` optional

Scope:

- `read`

#### `GET /api/agent/tasks/overdue`

Purpose:

- list active overdue tasks

Query params:

- `category` optional

Scope:

- `read`

#### `GET /api/agent/tasks/due-soon`

Purpose:

- list active tasks due within the requested number of hours

Query params:

- `hours` optional, default `24`
- `category` optional

Scope:

- `read`

### Task Mutation

#### `POST /api/agent/tasks`

Purpose:

- create a new task

Scope:

- `write`

Request body:

```json
{
  "title": "Review posture exercises",
  "description": "Quick daily mobility review",
  "category": "physical",
  "priority": 3,
  "due_date": "2026-04-03T20:00:00-04:00",
  "is_recurring": true,
  "recurrence_pattern": "daily"
}
```

Notes:

- task creation may trigger AI auto-tagging
- task creation does not fail if auto-tagging is unavailable

#### `PATCH /api/agent/tasks/{task_id}`

Purpose:

- update mutable fields on a task

Scope:

- `write`

#### `POST /api/agent/tasks/{task_id}/complete`

Purpose:

- complete a task
- logs a completion row
- applies points logic
- advances recurrence if needed

Scope:

- `write`

Request body:

```json
{
  "quality": 4,
  "notes": "Completed before dinner"
}
```

Response:

- completion summary including `points_earned`
- `next_due` if recurring

### Completion History

#### `GET /api/agent/completed`

Purpose:

- list completed tasks with task title/category attached

Query params:

- `limit` optional, default `50`
- `offset` optional, default `0`

Scope:

- `read`

#### `PATCH /api/agent/completed/{completion_id}`

Purpose:

- update notes for a completion record

Scope:

- `write`

### LLM Summary Views

#### `GET /api/agent/summary/domains`

Purpose:

- return the primary top-level domain breakdown for Hermes

Includes:

- active task counts by domain
- overdue task counts by domain
- due-soon task counts by domain
- recurring task counts
- completion counts
- total points by domain
- recent completions

Query params:

- `hours` optional, default `24`
- `recent_completion_limit` optional, default `10`

Scope:

- `read`

#### `GET /api/agent/summary/maintenance`

Purpose:

- return a compact operational snapshot for maintenance logic

Includes:

- total counts
- active/overdue/due-soon by category
- points by category
- overdue task list
- due-soon task list
- untagged active tasks
- stale active tasks
- recent completions

Query params:

- `hours` optional, default `24`
- `stale_days` optional, default `7`
- `recent_completion_limit` optional, default `10`

Scope:

- `read`

### Skill Tree

#### `GET /api/agent/skill-tree`

Purpose:

- return the Atma skill tree with domain rollups and tag hierarchy

Scope:

- `read`

## Why Hermes Should Use These Instead Of Public Routes

The public routes exist for the deployed website and current production behavior.

The agent routes are better for Hermes because:

- they are explicitly protected
- they are stable integration points for MCP
- they separate machine access from browser access
- they make future audit logging and policy checks easier

## Recommended Usage Pattern

Hermes should never call Atma directly from prompt logic.

Instead:

1. Hermes calls a local MCP tool on the ASUS laptop
2. the MCP wrapper adds the bearer token
3. the MCP wrapper calls `/api/agent/*`
4. Atma validates scope and executes the request

That gives you a clean control plane:

- public/frontend API remains intact
- agent automation goes through a dedicated interface
- secrets stay outside the model prompt layer
