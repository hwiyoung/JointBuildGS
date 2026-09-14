#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute attempt containing report/index.html}
test -s "$attempt/report/index.html"
docker run -d --name jbgs-source-selected-2dgs-8909 --read-only \
  --cpus 1 --memory 256m --memory-swap 256m --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:8909:8080 \
  --entrypoint python -v "$attempt:/payload:ro" \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  -m http.server 8080 --directory /payload
