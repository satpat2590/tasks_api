#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f ".env" ]]; then
  echo ".env not found. Copy .env.example to .env and fill in ATMA_BASE_URL / ATMA_BEARER_TOKEN."
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo ".venv is missing. Run: bash setup_popos.sh"
  exit 1
fi

set -a
source .env
set +a

exec .venv/bin/python atma_remote_server.py
