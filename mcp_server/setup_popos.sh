#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found."
  exit 1
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo
echo "Atma MCP setup complete."
echo "Next steps:"
echo "1. Copy .env.example to .env and set ATMA_BASE_URL / ATMA_BEARER_TOKEN"
echo "2. Run: bash run_atma_mcp.sh"
