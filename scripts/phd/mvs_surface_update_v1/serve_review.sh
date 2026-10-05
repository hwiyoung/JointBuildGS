#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute sealed attempt path}
test -s "$attempt/review/receipt.json"
docker run -d --name jbgs-mvs-surface-update-8908 --read-only \
  --cpus 1 --memory 256m --memory-swap 256m --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8908:8080 --entrypoint /opt/geogs/bin/python \
  -v "$attempt:/payload:ro" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  -m http.server 8080 --directory /payload
