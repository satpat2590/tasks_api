# ATMA MCP Server

## Purpose

This document explains how the ASUS laptop should talk to the production Atma service on Render through one local MCP wrapper without giving agents direct database access.

The recommended shape is:

- Atma stays a normal HTTPS API on Render
- Atma uses one bearer token trusted for the ASUS control plane
- a local MCP server runs on the ASUS laptop
- local agents talk to the local MCP server
- the MCP server calls Atma over HTTPS with the bearer token

This keeps the architecture simple and practical.

## Auth Model

### Atma-side auth

Atma now supports bearer-token agent auth with read/write scopes.

For your intended setup, you only need:

- `ATMA_HERMES_TOKEN`
  - one long-lived trusted token for the ASUS-side MCP wrapper

You do not need per-agent backend tokens if the ASUS laptop is one shared trusted control plane.

### MCP-side auth

The MCP server should store the Render API token in its own environment, for example:

- `ATMA_BASE_URL=https://your-render-service.onrender.com`
- `ATMA_BEARER_TOKEN=replace-with-your-shared-asus-token`

The MCP wrapper attaches it to outgoing HTTP calls.

## Why This Is The Right Boundary

This model is better than exposing raw database access because:

- Atma remains the source of truth
- Supabase credentials stay on the service side
- agents get structured tools, not open-ended DB power
- Atma can validate recurrence, points, due-state logic, and task mutations
- the laptop only needs one backend secret

## Flow

### Read flow

1. a local agent calls a tool like `atma_get_domain_summary`
2. local MCP server receives the tool call
3. MCP server sends `GET /api/agent/summary/domains` to Render
4. Atma authenticates the bearer token
5. Atma returns structured JSON
6. MCP server returns the result to the agent

### Write flow

1. a local agent calls a tool like `atma_create_task`
2. local MCP server sends `POST /api/agent/tasks`
3. Atma authenticates the token and validates the request
4. Atma writes to Supabase
5. Atma returns the created record
6. MCP server forwards the structured result

## Recommended Deployment Pattern

### Current recommendation

Use a **single local MCP wrapper on the ASUS laptop**.

Benefits:

- Atma deployment stays simple
- all local agents can share one tool server
- the bearer token stays in the ASUS-side runtime environment
- Atma remains protocol-agnostic at the cloud edge

### Later option

If you later want Atma itself to expose MCP remotely, that can be done using a Streamable HTTP MCP server. For now, that is not necessary.

## Official MCP Server Basis

The MCP wrapper scaffold in this repo is based on the official MCP Python SDK:

- the official Python SDK documents `FastMCP`
- tools are exposed with `@mcp.tool()`
- direct execution can be run with `mcp.run()`
- production-oriented MCP deployments can use Streamable HTTP

Primary sources:

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Model Context Protocol site](https://modelcontextprotocol.io)

## ASUS Laptop Setup

Use the self-contained [mcp_server](/Users/satya/tasks_api/mcp_server) folder.

The easiest setup steps are documented here:

- [ATMA_ASUS_TOKEN_SETUP.md](/Users/satya/tasks_api/docs/ATMA_ASUS_TOKEN_SETUP.md)
- [mcp_server/README.md](/Users/satya/tasks_api/mcp_server/README.md)

## Tool Mapping

The starter MCP server in this repo wraps the following Atma endpoints:

- `atma_whoami`
  - `GET /api/agent/me`
- `atma_list_active_tasks`
  - `GET /api/agent/tasks/remainder`
- `atma_list_overdue_tasks`
  - `GET /api/agent/tasks/overdue`
- `atma_list_due_soon_tasks`
  - `GET /api/agent/tasks/due-soon`
- `atma_get_domain_summary`
  - `GET /api/agent/summary/domains`
- `atma_get_maintenance_snapshot`
  - `GET /api/agent/summary/maintenance`
- `atma_get_skill_tree`
  - `GET /api/agent/skill-tree`
- `atma_list_completed_tasks`
  - `GET /api/agent/completed`
- `atma_create_task`
  - `POST /api/agent/tasks`
- `atma_update_task`
  - `PATCH /api/agent/tasks/{task_id}`
- `atma_complete_task`
  - `POST /api/agent/tasks/{task_id}/complete`

## Suggested Agent Registration

The MCP client config on the ASUS laptop should point local agents to the local wrapper process, not directly to Render.

Conceptually:

- command: `python`
- args: `["/path/to/atma_remote_server.py"]`
- env:
  - `ATMA_BASE_URL`
  - `ATMA_BEARER_TOKEN`

This way:

- agents get stable tools
- the token remains outside the prompt layer
- Atma remains remotely hosted

## Token Lifecycle

You do **not** need to rotate tokens routinely.

For your setup, the simplest model is:

- create one long-lived ASUS control-plane token
- store it in Render as the Atma-side trusted agent secret
- store the same token on the ASUS laptop as the MCP-side outgoing bearer token
- leave it alone unless there is a real reason to replace it

You would only rotate the token if:

- the ASUS laptop is lost or compromised
- the token leaks into logs, code, or chat history
- you retire Hermes and replace it with another control path
- you intentionally want to revoke old access

So rotation is an emergency/revocation tool, not a daily or weekly maintenance task.

If the ASUS laptop is one trusted control plane, a single stable token is completely reasonable.

## Operational Notes

- use long random secrets for all agent tokens
- do not reuse Supabase keys as agent tokens
- do not expose the bearer token in tool outputs
- keep the MCP wrapper stateless
- let Atma remain the only writer of canonical task truth

## Tool Separation By Agent

Since the ASUS laptop is one trusted local system, the recommended separation is:

- one MCP wrapper with the full Atma tool surface
- different tool bundles exposed to different agents

Example:

- `Satya`
  - read + write Atma tools
- `Argus`
  - read-only Atma tools

This is a clean policy boundary even if it is not meant to be a hard local-security boundary.

## Future Upgrade Path

If you later decide to expose MCP directly from Atma:

- keep the same Atma business endpoints and logic
- either wrap them internally as MCP tools or mount a dedicated MCP app
- add MCP-native auth at that layer

For now, the local ASUS-side wrapper is the cleaner and safer approach.
