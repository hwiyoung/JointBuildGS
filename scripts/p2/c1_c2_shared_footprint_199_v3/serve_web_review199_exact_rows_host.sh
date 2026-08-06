#!/usr/bin/env bash
set -euo pipefail

artifact_root="${1:?usage: serve_web_review199_exact_rows_host.sh ARTIFACT_ROOT [PORT] [BIND_HOST]}"
port="${2:-8765}"
bind_host="${3:-0.0.0.0}"
task_rel="phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-ORIGINAL-GLOBAL-v3-WEB-REVIEW199-EXACT-V6V4-ROWS-COMPACT-FIT-v11"
viewer_root="${artifact_root}/${task_rel}"
image="jointbuildgs-p0-tools:t0"
expected_image_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"

[[ "${artifact_root}" == /* && -d "${viewer_root}" ]] || { echo "exact-row web review199 package is missing" >&2; exit 2; }
[[ "${port}" =~ ^[0-9]{4,5}$ && "${port}" -ge 1024 && "${port}" -le 65535 ]] || { echo "invalid port" >&2; exit 2; }
[[ "${bind_host}" == "0.0.0.0" || "${bind_host}" == "127.0.0.1" ]] || { echo "bind host must be 0.0.0.0 or 127.0.0.1" >&2; exit 2; }
[[ "$(docker image inspect "${image}" --format '{{.Id}}')" == "${expected_image_id}" ]] || { echo "p0-tools image identity mismatch" >&2; exit 2; }

echo "Serving exact-row web review199 on ${bind_host}:${port}"
echo "Local URL: http://127.0.0.1:${port}/"
if [[ "${bind_host}" == "0.0.0.0" ]]; then
  echo "LAN URL: http://HOST_LAN_IP:${port}/ (no authentication; trusted LAN only)"
fi
docker run --rm --network bridge --entrypoint /bin/sh \
  --user "$(id -u):$(id -g)" --cpus 2 --memory 2g --pids-limit 256 \
  -p "${bind_host}:${port}:8765" \
  -v "${viewer_root}:/viewer:ro" \
  -w /viewer "${image}" -lc \
  "python -m http.server 8765 --bind 0.0.0.0 --directory /viewer"
