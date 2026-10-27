#!/usr/bin/env bash
# Build with the host's supported proxy and trust configuration, when present.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export DOCKER_CONFIG="${DOCKER_CONFIG:-/tmp/quantpilot-docker}"
override=$(mktemp /tmp/quantpilot-compose.XXXXXX.json)
trap 'rm -f "$override"' EXIT
python3 - "$override" <<'PY'
import json
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

hosts = {}
for name in ("HTTP_PROXY", "HTTPS_PROXY"):
    hostname = urlsplit(os.environ.get(name, "")).hostname
    if hostname:
        hosts[hostname] = socket.gethostbyname(hostname)
build = {"extra_hosts": hosts}
config = {"services": {"api": {"build": build}, "web": {"build": build}, "worker": {"build": build}}}
certificate = os.environ.get("SSL_CERT_FILE")
if certificate and Path(certificate).is_file():
    build["secrets"] = ["environment_ca"]
    config["secrets"] = {"environment_ca": {"file": certificate}}
Path(sys.argv[1]).write_text(json.dumps(config))
PY
docker compose -f docker-compose.yml -f "$override" build \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY
