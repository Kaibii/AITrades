#!/usr/bin/env bash
set -euo pipefail
cd /workspace/AITrades
export UV_CACHE_DIR=/tmp/quantpilot-uv
uv sync --frozen
npm --prefix apps/web ci --cache /tmp/quantpilot-npm
