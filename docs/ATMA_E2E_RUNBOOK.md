# ATMA E2E Runbook

## Purpose

This runbook is the shortest path from the current Atma codebase to a working end-to-end setup where:

- Atma runs on Render
- Atma stores data in Supabase
- Atma exposes protected `/api/agent/*` endpoints
- one MCP wrapper runs on the ASUS laptop
- Satya and Argus both use that MCP wrapper
- Satya gets read/write Atma tools
- Argus gets read-only Atma tools

This is the intended simple model:

- one trusted ASUS control plane
- one shared Atma bearer token
- one MCP server
- different tool bundles per agent

## Architecture

The request path should look like this:

1. local agent on ASUS calls a tool
2. local MCP server receives the tool call
3. MCP server sends HTTPS request to Atma on Render
4. Atma validates the bearer token
5. Atma executes domain logic against Supabase
6. Atma returns JSON to the MCP server
7. MCP server returns structured tool output to the agent

## What You Need

Before starting, make sure you have:

- Render access for the Atma service
- ASUS laptop shell access
- the current Atma repo on the Mac Mini
- the `mcp_server/` folder available to copy to ASUS

## Step 1: Generate One Token

Generate one long random token:

```bash
openssl rand -hex 32
```

Example:

```text
4f7b1c6b4c7c8b8b2f9db85f9d1ce7f4a7176e80c8c4d1d3d0b9a1e9a8c0de11
```

This is your shared ASUS-to-Atma bearer token.

## Step 2: Configure Render

In the Render dashboard for the Atma backend, set:

```text
ATMA_HERMES_TOKEN=<your-generated-token>
```

Keep your existing Supabase vars in place.

You should already have:

```text
SUPABASE_URL=...
SUPABASE_API_KEY=...
```

or:

```text
SUPABASE_URL=...
SUPABASE_KEY=...
```

After setting the token:

1. save the env var
2. redeploy or restart the Render service

## Step 3: Confirm Atma Deploys Cleanly

Once Render redeploys, verify the service still responds on the public side.

Examples:

```bash
curl https://your-render-service.onrender.com/
curl https://your-render-service.onrender.com/api/tasks
```

These should still work without bearer auth.

## Step 4: Copy The MCP Folder To ASUS

From this repo, copy the full [mcp_server](/Users/satya/tasks_api/mcp_server) folder to the ASUS laptop.

Recommended destination:

```bash
~/atma-mcp
```

The folder you need is self-contained:

- [mcp_server/README.md](/Users/satya/tasks_api/mcp_server/README.md)
- [mcp_server/atma_remote_server.py](/Users/satya/tasks_api/mcp_server/atma_remote_server.py)
- [mcp_server/requirements.txt](/Users/satya/tasks_api/mcp_server/requirements.txt)
- [mcp_server/.env.example](/Users/satya/tasks_api/mcp_server/.env.example)
- [mcp_server/setup_popos.sh](/Users/satya/tasks_api/mcp_server/setup_popos.sh)
- [mcp_server/run_atma_mcp.sh](/Users/satya/tasks_api/mcp_server/run_atma_mcp.sh)

## Step 5: Configure ASUS Environment

On the ASUS laptop:

```bash
cd ~/atma-mcp
cp .env.example .env
```

Edit `.env` so it contains:

```bash
ATMA_BASE_URL=https://your-render-service.onrender.com
ATMA_BEARER_TOKEN=<your-generated-token>
ATMA_HTTP_TIMEOUT=30
```

That is the only MCP-side secret/config you need.

## Step 6: Install The MCP Wrapper On Pop!OS

From the ASUS laptop:

```bash
cd ~/atma-mcp
bash setup_popos.sh
```

This creates `.venv` and installs dependencies.

## Step 7: Smoke Test The Token Before MCP

Still on ASUS:

```bash
cd ~/atma-mcp
set -a
source .env
set +a
curl -H "Authorization: Bearer $ATMA_BEARER_TOKEN" "$ATMA_BASE_URL/api/agent/me"
```

Expected result:

```json
{
  "agent": "hermes",
  "scopes": ["read", "write"]
}
```

If you get that, the token path is correct.

## Step 8: Smoke Test An Agent Read Endpoint

Run:

```bash
curl -H "Authorization: Bearer $ATMA_BEARER_TOKEN" "$ATMA_BASE_URL/api/agent/summary/domains"
```

Expected result:

- JSON response
- includes:
  - `generated_at`
  - `totals`
  - `domains`
  - `recent_completions`

## Step 9: Start The MCP Server

On ASUS:

```bash
cd ~/atma-mcp
bash run_atma_mcp.sh
```

That launches the stdio MCP wrapper process.

If you are using a tool runner or an agent platform, that platform should normally launch this process for you.

## Step 10: Register The MCP Server With Your Agents

Your local agent platform should point both Satya and Argus to the same MCP process:

- command: `python`
- args: `["/path/to/atma_remote_server.py"]`
- env:
  - `ATMA_BASE_URL`
  - `ATMA_BEARER_TOKEN`

If the platform can invoke the shell script directly, that is also acceptable:

- command: `bash`
- args: `["/path/to/run_atma_mcp.sh"]`

## Step 11: Tool Bundle Split

This is where Satya vs Argus differs.

### Satya tool bundle

Give Satya:

- `atma_whoami`
- `atma_list_active_tasks`
- `atma_list_overdue_tasks`
- `atma_list_due_soon_tasks`
- `atma_get_domain_summary`
- `atma_get_maintenance_snapshot`
- `atma_get_skill_tree`
- `atma_list_completed_tasks`
- `atma_create_task`
- `atma_update_task`
- `atma_complete_task`

### Argus tool bundle

Give Argus:

- `atma_whoami`
- `atma_list_active_tasks`
- `atma_list_overdue_tasks`
- `atma_list_due_soon_tasks`
- `atma_get_domain_summary`
- `atma_get_maintenance_snapshot`
- `atma_get_skill_tree`
- `atma_list_completed_tasks`

Argus should not be shown:

- `atma_create_task`
- `atma_update_task`
- `atma_complete_task`

## Step 12: First E2E Agent Tests

Run these tests in order.

### Test 1: Identity

Ask Satya:

```text
Use the Atma tool to verify which identity you are using.
```

Expected behavior:

- Satya calls `atma_whoami`
- Satya reports the agent identity and scopes

### Test 2: Read summary

Ask Argus:

```text
Use Atma to summarize my current domain state.
```

Expected behavior:

- Argus calls `atma_get_domain_summary`
- Argus reports active, overdue, and points by domain

### Test 3: Read task state

Ask Satya:

```text
Use Atma to list overdue tasks and tasks due soon.
```

Expected behavior:

- Satya calls:
  - `atma_list_overdue_tasks`
  - `atma_list_due_soon_tasks`

### Test 4: Safe write

Ask Satya:

```text
Create a daily physical task called "Review posture exercises" due tonight at 8 PM Eastern.
```

Expected behavior:

- Satya calls `atma_create_task`
- Atma stores the task
- Atma returns the created task record

### Test 5: Confirm Argus does not write

Ask Argus:

```text
Create a new task in Atma.
```

Expected behavior:

- Argus should not have a write tool available
- it should say it cannot perform that write action directly

## Minimal Operational Workflow

Once the above works, your steady-state workflow is:

1. Atma stays deployed on Render
2. Supabase stays the source of truth
3. ASUS runs one MCP wrapper
4. Satya gets read/write tool visibility
5. Argus gets read-only tool visibility

That is the simplest long-term operating model.

## Troubleshooting

### `503 Agent auth is not configured on this Atma service`

Cause:

- Render does not have `ATMA_HERMES_TOKEN` set
- or the service has not restarted after setting it

Fix:

1. add `ATMA_HERMES_TOKEN` in Render
2. redeploy/restart

### `401 Bearer token required` or `401 Invalid agent token`

Cause:

- ASUS `.env` token does not match Render
- or `.env` is not being loaded

Fix:

1. confirm `.env` exists
2. confirm `ATMA_BEARER_TOKEN` matches Render exactly
3. rerun the `curl /api/agent/me` test

### Public site stops working

Cause:

- Render deploy failed
- unrelated env issue

Fix:

1. check Render logs
2. verify `/` and `/api/tasks` still respond publicly

The public site should remain unaffected because the public endpoints are still open.

### MCP server does not start on ASUS

Cause:

- dependencies not installed
- `.env` missing
- wrong Python path

Fix:

1. run `bash setup_popos.sh`
2. verify `.env` exists
3. run `bash run_atma_mcp.sh`

### Agent can write when it should not

Cause:

- write tools were exposed in that agent’s config/context

Fix:

- remove `atma_create_task`
- remove `atma_update_task`
- remove `atma_complete_task`

This is controlled by tool exposure, not by separate backend identities.

## Reference Docs

For supporting detail:

- [ATMA_AGENT_ENDPOINTS.md](/Users/satya/tasks_api/docs/ATMA_AGENT_ENDPOINTS.md)
- [ATMA_MCP_SERVER.md](/Users/satya/tasks_api/docs/ATMA_MCP_SERVER.md)
- [ATMA_ASUS_TOKEN_SETUP.md](/Users/satya/tasks_api/docs/ATMA_ASUS_TOKEN_SETUP.md)
- [mcp_server/README.md](/Users/satya/tasks_api/mcp_server/README.md)
