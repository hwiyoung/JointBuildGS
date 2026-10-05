#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?Provide the completed attempt directory containing evidence and review output}
review_name=${2:-review_v2}
test -f "$attempt/$review_name/receipt.json"
docker run -d --name jbgs-mvs-evidence-8907 --restart unless-stopped \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" --cpus 1 --memory 256m \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -p 127.0.0.1:8907:8080 -v "$attempt:/payload:ro" \
  --entrypoint /opt/geogs/bin/python \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  -m http.server 8080 --directory /payload
printf 'http://127.0.0.1:8907/%s/\n' "$review_name"
