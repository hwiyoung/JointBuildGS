#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
artifact_root="${JBGS_ARTIFACT_ROOT_HOST:-$(realpath "${repo_root}/../JointBuildGS-artifacts")}"
viewer_root="${artifact_root}/phase-payloads/phd/mvs_als_surface_patch_v1/PHD-MVS-ALS-SURFACE-PATCH-v1/viewer"
viewer_port="${JBGS_SURFACE_PATCH_VIEWER_PORT:-8892}"
container_name="jbgs-mvs-als-surface-patch-viewer-${viewer_port}"

test -f "${viewer_root}/viewer_manifest.json"

if docker inspect "${container_name}" >/dev/null 2>&1; then
  state="$(docker inspect "${container_name}" --format '{{.State.Status}}')"
  if [[ "${state}" != "running" ]]; then
    docker start "${container_name}" >/dev/null
  fi
else
  docker run -d \
    --name "${container_name}" \
    -p "${viewer_port}:8080" \
    -v "${viewer_root}:/srv:ro" \
    -w /srv \
    jointbuildgs:dev \
    python -m http.server 8080 --bind 0.0.0.0 >/dev/null
fi

printf 'MVS-ALS surface-patch viewer: http://127.0.0.1:%s/\n' "${viewer_port}"
