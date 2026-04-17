#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export OBSIDIAN_VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
exec uv run python server.py
