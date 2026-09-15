#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute attempt path}
test -s "$attempt/report/index.html"
test -s "$attempt/source_snapshot/scripts/phd/irregular_source_masks_v1/serve.py"
docker run -d --name jbgs-irregular-source-masks-8911 --read-only \
  --cpus 2 --memory 4g --memory-swap 4g --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:8911:8080 \
  --entrypoint /opt/geogs/bin/python -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$attempt:/payload:ro" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  /payload/source_snapshot/scripts/phd/irregular_source_masks_v1/serve.py --root /payload
