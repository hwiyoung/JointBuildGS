#!/usr/bin/env bash
set -euo pipefail

artifact_root="${1:?usage: serve_web_host.sh ARTIFACT_ROOT [PORT]}"
port="${2:-8877}"
package="${artifact_root}/phase-payloads/p2/c2_c3_rendered_depth_shared_footprint_199_v1/P2-C2-C3-RENDERED-DEPTH-SHARED-FOOTPRINT-199-WEB-v2"
name="jbgs-c2-c3-rendered-depth-web-v2-${port}"
[[ -f "${package}/manifest_web_v1.json" && -f "${package}/viewer_manifest.json" ]] || { echo "viewer package is incomplete" >&2; exit 2; }
[[ "${port}" != "8876" ]] || { echo "port 8876 is protected until final approval" >&2; exit 2; }
if docker container inspect "${name}" >/dev/null 2>&1; then
  echo "viewer container already exists: ${name}"
  exit 0
fi
docker run -d --name "${name}" --restart unless-stopped \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --user "$(id -u):$(id -g)" -p "${port}:8765" \
  -v "${package}:/viewer:ro" -w /viewer jointbuildgs-p0-tools:t0 \
  python -B -m http.server 8765 --bind 0.0.0.0
echo "temporary viewer: http://192.168.10.203:${port}/"
