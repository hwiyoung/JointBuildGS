#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
relative_root="phase-payloads/p2/c3_roof_texture_reference_extension_v1/P2-C3-ROOF-TEXTURE-C1-LOD2-REFERENCE-EXTENSION-v5"
final_root="${artifact_root}/${relative_root}"
partial_root="${final_root}.partial"
project_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_roofer_id="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"

[[ -z "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]] || { echo "clean source required" >&2; exit 2; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "$(git -C "${repo_root}" rev-parse origin/main)" ]] || { echo "HEAD must equal origin/main" >&2; exit 2; }
[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${project_image}" ]] || { echo "project image mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${roofer_image}" --format '{{.Id}}')" == "${expected_roofer_id}" ]] || { echo "Roofer image mismatch" >&2; exit 2; }
[[ ! -e "${final_root}" && ! -e "${partial_root}" ]] || { echo "add-once v5 namespace exists" >&2; exit 2; }

source_commit="$(git -C "${repo_root}" rev-parse HEAD)"
docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS:rw" "${project_image}" \
  sh -lc "install -d -o $(id -u) -g $(id -g) -m 0755 '/artifacts/JointBuildGS/${relative_root}.partial'"

project_run() {
  docker run --rm --network none --cpus 4 --memory 32g --pids-limit 1024 \
    --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
    -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS:rw" \
    -w /workspace/JointBuildGS "${project_image}" -B \
    scripts/p2/c3_roof_texture_reference_extension_v1/recover_v5.py "$@"
}

project_run prepare --output-root "/artifacts/JointBuildGS/${relative_root}.partial" --artifact-root /artifacts/JointBuildGS --source-commit "${source_commit}"

work="${partial_root}/operations/C1_LIDAR_LOD2_GROUND_Z_ORACLE/DEBY_LOD2_4907177/work"
mkdir "${work}/out"
begin="${SECONDS}"
set +e
timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
  --user "$(id -u):$(id -g)" -v "${work}:/work:rw" -w /work "${roofer_image}" \
  --id-attribute stable_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
  input.las gt_footprint_oracle.geojson out >"${work}/runtime.log" 2>&1
exit_code=$?
set -e
runtime_seconds="$((SECONDS - begin))"
project_run record-terminal --output-root "/artifacts/JointBuildGS/${relative_root}.partial" --exit-code "${exit_code}" --runtime-seconds "${runtime_seconds}"
project_run render-and-finalize --output-root "/artifacts/JointBuildGS/${relative_root}.partial" --artifact-root /artifacts/JointBuildGS --source-commit "${source_commit}"

docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS:rw" "${project_image}" \
  sh -lc "mv -- '/artifacts/JointBuildGS/${relative_root}.partial' '/artifacts/JointBuildGS/${relative_root}'"
echo "completed: ${final_root}"
