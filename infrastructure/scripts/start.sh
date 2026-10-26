#!/usr/bin/env bash
# Use the existing checkout; cloud tasks are already isolated.
set -euo pipefail
cd /workspace/AITrades
export DOCKER_CONFIG=/tmp/quantpilot-docker
bash infrastructure/scripts/build.sh
docker compose up -d --no-build --wait
.venv/bin/python infrastructure/scripts/smoke.py
