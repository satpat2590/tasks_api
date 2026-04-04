# ATMA ASUS Token Setup

## Purpose

This document shows the practical setup for giving the ASUS laptop MCP wrapper access to the production Atma backend with the least friction possible.

The goal is simple:

- Render trusts one ASUS-side MCP token
- the ASUS laptop stores that same token locally
- the MCP wrapper sends it as a bearer token on every `/api/agent/*` request

This is a server-to-server secret, not a browser secret.

## Mental Model

There are two sides to the same token:

### Atma side

Render stores the trusted secret in the Atma service environment.

### ASUS side

The ASUS laptop stores the same secret in the MCP wrapper environment and sends:

```http
Authorization: Bearer <your-token>
```

If both sides match, the ASUS MCP wrapper gets access to the protected agent endpoints.

## Recommended Simple Setup

For your current system, use a single long-lived ASUS control-plane token.

Recommended names:

- Render:
  - `ATMA_HERMES_TOKEN`
- ASUS laptop:
  - `ATMA_BEARER_TOKEN`

The values should be the same exact secret.

## Step 1: Generate A Token

Generate a long random string on a trusted machine:

```bash
openssl rand -hex 32
```

Example output:

```text
4f7b1c6b4c7c8b8b2f9db85f9d1ce7f4a7176e80c8c4d1d3d0b9a1e9a8c0de11
```

That full string is your Atma MCP token.

## Step 2: Configure Render

In the Render dashboard for the Atma service, add:

```text
ATMA_HERMES_TOKEN=<your-generated-token>
```

Then redeploy or restart the service.

After that, the Atma backend will accept this token for `/api/agent/*`.

## Step 3: Configure The ASUS Laptop

On the ASUS laptop, the MCP wrapper needs:

```bash
export ATMA_BASE_URL="https://your-render-service.onrender.com"
export ATMA_BEARER_TOKEN="<your-generated-token>"
```

You can place these in the shell rc for the dedicated user that runs Hermes, or in a service env file.

If you use `~/.zshrc` or `~/.bashrc`, add:

```bash
export ATMA_BASE_URL="https://your-render-service.onrender.com"
export ATMA_BEARER_TOKEN="<your-generated-token>"
```

Then reload the shell:

```bash
source ~/.zshrc
```

or:

```bash
source ~/.bashrc
```

## Step 4: Move The MCP Folder To The ASUS Laptop

Copy the full [mcp_server](/Users/satya/tasks_api/mcp_server) folder to the ASUS laptop.

The folder is intended to be portable and self-contained.

You should copy:

- [atma_remote_server.py](/Users/satya/tasks_api/mcp_server/atma_remote_server.py)
- [requirements.txt](/Users/satya/tasks_api/mcp_server/requirements.txt)
- [README.md](/Users/satya/tasks_api/mcp_server/README.md)
- [.env.example](/Users/satya/tasks_api/mcp_server/.env.example)
- [setup_popos.sh](/Users/satya/tasks_api/mcp_server/setup_popos.sh)
- [run_atma_mcp.sh](/Users/satya/tasks_api/mcp_server/run_atma_mcp.sh)

The docs in `/docs` are still useful reference material, but they are not required to launch the wrapper.

## Step 5: Create A Dedicated MCP Environment On ASUS

On the ASUS laptop:

```bash
mkdir -p ~/atma-mcp
cd ~/atma-mcp
bash setup_popos.sh
```

Note:

- keep this MCP wrapper in its own environment
- do not mix it into the Atma backend environment

## Step 6: Verify The Token Locally

Before wiring Hermes to MCP, test the token with `curl`:

```bash
curl \
  -H "Authorization: Bearer $ATMA_BEARER_TOKEN" \
  "$ATMA_BASE_URL/api/agent/me"
```

Expected response:

```json
{
  "agent": "hermes",
  "scopes": ["read", "write"]
}
```

If this works, the ASUS laptop is correctly authenticated to Atma.

## Step 7: Run The MCP Wrapper

From the ASUS laptop MCP directory:

```bash
bash run_atma_mcp.sh
```

The MCP client will launch it as a local process and communicate over stdio.

## Agent Configuration Shape

Satya, Argus, or any other local agent should connect to the MCP wrapper process, not directly to Render.

Conceptually:

- command: `python`
- args: `["/path/to/atma_remote_server.py"]`
- env:
  - `ATMA_BASE_URL`
  - `ATMA_BEARER_TOKEN`

That means:

- the local agent gets tools
- the agent does not need the raw backend internals
- the token stays in the local runtime environment

## What Secret Lives Where

### Safe places

- Render environment variables
- ASUS laptop shell/service environment
- password manager
- encrypted secrets manager

### Unsafe places

- browser frontend code
- git-tracked config files
- screenshots
- prompt text
- logs returned to the model

## Single-MCP Setup

For your current system, the cleanest configuration is:

- one token
- one MCP wrapper
- one Atma production backend
- multiple local agents using the same MCP server

Tool separation should happen in agent context:

- Satya gets read + write Atma tools
- Argus gets read-only Atma tools

That is the intended policy split.

## When To Change The Token

You only need to replace the token if:

- the ASUS laptop is compromised
- the token leaks
- you want to revoke an old integration

Otherwise, keep it stable.

## Quick Checklist

1. Generate one long random token.
2. Put it in Render as `ATMA_HERMES_TOKEN`.
3. Put the same value on the ASUS laptop as `ATMA_BEARER_TOKEN`.
4. Set `ATMA_BASE_URL` on the ASUS laptop.
5. Copy the `mcp_server/` folder to the ASUS laptop.
6. Run `bash setup_popos.sh`.
7. Test `/api/agent/me` with `curl`.
8. Run `bash run_atma_mcp.sh`.
9. Connect Satya and Argus to the local MCP process with different tool bundles.
