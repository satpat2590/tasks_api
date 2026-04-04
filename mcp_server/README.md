# Atma MCP Server

## What This Is

This folder is the ASUS-side MCP wrapper for Atma.

You can copy this folder onto the ASUS laptop and run it independently of the main Atma backend repo.

The intended model is:

- Atma backend stays on Render
- this MCP wrapper runs locally on the ASUS laptop
- the wrapper uses one shared Atma bearer token
- all local agents can use this MCP server
- tool separation happens in agent context, not backend auth

That means:

- `Satya` can be shown both read and write Atma tools
- `Argus` can be shown only read tools

## Files

- `atma_remote_server.py`
  - MCP wrapper process
- `requirements.txt`
  - Python dependencies
- `.env.example`
  - environment variable template
- `setup_popos.sh`
  - one-time setup helper for Pop!OS / Ubuntu-style Linux
- `run_atma_mcp.sh`
  - starts the MCP wrapper using the local virtualenv

## Pop!OS Setup

### 1. Copy this folder to the ASUS laptop

Recommended destination:

```bash
~/atma-mcp
```

### 2. Enter the folder

```bash
cd ~/atma-mcp
```

### 3. Create your env file

```bash
cp .env.example .env
```

Edit `.env` so it contains:

```bash
ATMA_BASE_URL=https://your-render-service.onrender.com
ATMA_BEARER_TOKEN=replace-with-your-token
ATMA_HTTP_TIMEOUT=30
```

### 4. Run setup

```bash
bash setup_popos.sh
```

This will:

- create `.venv`
- install Python dependencies

### 5. Verify the token

```bash
source .venv/bin/activate
set -a
source .env
set +a
curl -H "Authorization: Bearer $ATMA_BEARER_TOKEN" "$ATMA_BASE_URL/api/agent/me"
```

Expected response:

```json
{
  "agent": "hermes",
  "scopes": ["read", "write"]
}
```

### 6. Run the MCP server

```bash
bash run_atma_mcp.sh
```

## Hermes / Agent Usage Model

This MCP server exposes the full Atma agent tool surface.

You should decide which tools each agent sees in its own config or prompt context.

### Suggested Satya tool bundle

Give Satya all of these:

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

### Suggested Argus tool bundle

Give Argus only these:

- `atma_whoami`
- `atma_list_active_tasks`
- `atma_list_overdue_tasks`
- `atma_list_due_soon_tasks`
- `atma_get_domain_summary`
- `atma_get_maintenance_snapshot`
- `atma_get_skill_tree`
- `atma_list_completed_tasks`

## Important Note

This is a policy boundary, not a hard local security boundary.

Since the ASUS laptop is one trusted control plane, the goal is:

- keep the setup simple
- keep Atma domain logic behind the backend API
- avoid direct Supabase access from agents

## Manual Run

If you do not want to use the helper scripts:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python atma_remote_server.py
```
