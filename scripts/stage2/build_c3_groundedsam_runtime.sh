#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
base_tag="jointbuildgs:dev"
base_id="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
target_tag="jointbuildgs:c3-groundedsam-v1"
expected_target_id="sha256:7217f813ecf7f690816341bb9cdf6fd80928e635d7edb1ce420ae2561b2c7b79"
requirements="${repo_root}/requirements-c3-semantic.txt"
expected_requirements_sha="399b3860c291e6685bc63c3704bf34b1a6b1ef9a5c59e1ede6e583433d36a063"
dockerfile="${repo_root}/Dockerfile.c3-semantic"
expected_dockerfile_sha="a7b474d3577f66649e6d5c83ad846592e5434b635a65a7bd903c68579dc422e2"

actual_base_id="$(docker image inspect --format '{{.Id}}' "${base_tag}")"
if [[ "${actual_base_id}" != "${base_id}" ]]; then
    echo "base image ID mismatch: ${actual_base_id} != ${base_id}" >&2
    exit 2
fi

requirements_sha="$(sha256sum "${requirements}" | awk '{print $1}')"
if [[ "${requirements_sha}" != "${expected_requirements_sha}" ]]; then
    echo "requirements SHA mismatch: ${requirements_sha} != ${expected_requirements_sha}" >&2
    exit 3
fi

dockerfile_sha="$(sha256sum "${dockerfile}" | awk '{print $1}')"
if [[ "${dockerfile_sha}" != "${expected_dockerfile_sha}" ]]; then
    echo "Dockerfile SHA mismatch: ${dockerfile_sha} != ${expected_dockerfile_sha}" >&2
    exit 4
fi

if target_id="$(docker image inspect --format '{{.Id}}' "${target_tag}" 2>/dev/null)"; then
    if [[ "${target_id}" != "${expected_target_id}" ]]; then
        echo "existing runtime tag has mismatched ID: ${target_id} != ${expected_target_id}" >&2
        echo "refusing to rebuild or overwrite the existing tag" >&2
        exit 5
    fi
    build_status="REUSED_EXACT_NO_REBUILD"
else
    # The pinned target used the byte-identical historical Dockerfile and its
    # historical COPY path. Reconstruct only that minimal build context; no
    # legacy lock or receipt is read or modified by the C3 runtime contract.
    build_context="$(mktemp -d)"
    trap 'rm -rf -- "${build_context}"' EXIT
    mkdir -p "${build_context}/phases/p2-gsjso/docker/pilot-groundedsam"
    cp -- "${requirements}" \
        "${build_context}/phases/p2-gsjso/docker/pilot-groundedsam/requirements-runtime.txt"

    docker build \
        --file "${dockerfile}" \
        --tag "${target_tag}" \
        --build-arg "BASE_IMAGE=${base_tag}" \
        --build-arg "BASE_IMAGE_ID=${base_id}" \
        --build-arg "GROUNDINGDINO_REVISION=856dde20aee659246248e20734ef9ba5214f5e44" \
        --build-arg "SEGMENT_ANYTHING_REVISION=dca509fe793f601edb92606367a655c15ac00fdf" \
        --build-arg "RUNTIME_REQUIREMENTS_SHA256=${requirements_sha}" \
        "${build_context}"

    target_id="$(docker image inspect --format '{{.Id}}' "${target_tag}")"
    if [[ "${target_id}" != "${expected_target_id}" ]]; then
        echo "runtime image ID mismatch: ${target_id} != ${expected_target_id}" >&2
        exit 6
    fi
    build_status="BUILT_ABSENT_TAG"
fi

docker run --rm \
    --entrypoint python \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    "${target_tag}" \
    -c 'import json; from pathlib import Path; from src.stage2.c3_image_semantic_assets import audit_c3_runtime, load_c3_contract; contract=load_c3_contract(Path("/workspace/JointBuildGS/configs/stage2/c3_image_semantic_runtime_v1.json")); print(json.dumps(audit_c3_runtime(contract), sort_keys=True))'

printf 'status=%s\nruntime_tag=%s\nruntime_id=%s\nbase_id=%s\nrequirements_sha256=%s\n' \
    "${build_status}" "${target_tag}" "${target_id}" "${base_id}" "${requirements_sha}"
