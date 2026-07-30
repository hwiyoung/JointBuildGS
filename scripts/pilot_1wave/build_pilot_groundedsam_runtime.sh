#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
base_tag="jointbuildgs:dev"
base_id="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
target_tag="jointbuildgs:p1w-groundedsam-v1"
expected_runtime_id="sha256:3622911fb15eb2f460637f5c3f7f34f2790f5957b0475d1827d6c0a3e5dc88b1"
dino_revision="856dde20aee659246248e20734ef9ba5214f5e44"
sam_revision="dca509fe793f601edb92606367a655c15ac00fdf"
dockerfile="${repo_root}/phases/p2-gsjso/docker/pilot-groundedsam/Dockerfile"
requirements="${repo_root}/phases/p2-gsjso/docker/pilot-groundedsam/requirements-runtime.txt"

actual_base_id="$(docker image inspect --format '{{.Id}}' "${base_tag}")"
if [[ "${actual_base_id}" != "${base_id}" ]]; then
    echo "base image ID mismatch: ${actual_base_id} != ${base_id}" >&2
    exit 2
fi

requirements_sha256="$(sha256sum "${requirements}" | awk '{print $1}')"
docker build \
    --file "${dockerfile}" \
    --tag "${target_tag}" \
    --build-arg "BASE_IMAGE=${base_tag}" \
    --build-arg "BASE_IMAGE_ID=${base_id}" \
    --build-arg "GROUNDINGDINO_REVISION=${dino_revision}" \
    --build-arg "SEGMENT_ANYTHING_REVISION=${sam_revision}" \
    --build-arg "RUNTIME_REQUIREMENTS_SHA256=${requirements_sha256}" \
    "${repo_root}"

runtime_id="$(docker image inspect --format '{{.Id}}' "${target_tag}")"
if [[ "${runtime_id}" != "${expected_runtime_id}" ]]; then
    echo "runtime image ID changed: ${runtime_id} != ${expected_runtime_id}" >&2
    echo "inspect the build and explicitly repin the runtime lock" >&2
    exit 3
fi
printf 'runtime_tag=%s\nruntime_id=%s\nbase_id=%s\nrequirements_sha256=%s\n' \
    "${target_tag}" "${runtime_id}" "${base_id}" "${requirements_sha256}"
