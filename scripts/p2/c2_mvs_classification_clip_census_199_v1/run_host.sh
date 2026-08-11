#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:-$(realpath "$repo_root/../JointBuildGS-artifacts")}" 
config_rel="configs/p2/c2_mvs_classification_clip_census_199_v1/census_v1.json"
task_rel="phase-payloads/p2/c2_mvs_classification_clip_census_199_v1/P2-C2-MVS-CLASSIFICATION-CLIP-CENSUS-199-v1"
output_root="$artifact_root/$task_rel"
formal_rel="phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3"
classified_rel="$formal_rel/work/C2_MVS/classified_scene.laz"
footprint_rel="$formal_rel/freeze/shared_footprints_199.geojson"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
tools_image="jointbuildgs-p0-tools:t0"
source_commit="$(git -C "$repo_root" rev-parse HEAD)"
run_user="$(id -u):$(id -g)"

if [[ -e "$output_root" ]]; then
  echo "fresh add-once output required: $output_root" >&2
  exit 2
fi
mkdir -p "$output_root"

docker run --rm --user "$run_user" \
  -v "$repo_root:/workspace/JointBuildGS:ro" \
  -v "$artifact_root:/artifacts/JointBuildGS:ro" \
  -v "$output_root:/task" \
  -w /workspace/JointBuildGS \
  "$tools_image" \
  python scripts/p2/c2_mvs_classification_clip_census_199_v1/analyze.py prepare \
    --config "/workspace/JointBuildGS/$config_rel" \
    --artifact-root /artifacts/JointBuildGS \
    --output-root /task \
    --source-commit "$source_commit"

mkdir -p "$output_root/runs/clip_true" "$output_root/runs/clip_false"

for arm in clip_true clip_false; do
  extra_args=()
  if [[ "$arm" == "clip_false" ]]; then
    extra_args+=(--no-clip-terrain)
  fi
  start_seconds=$SECONDS
  set +e
  docker run --rm --user "$run_user" \
    -v "$artifact_root:/artifacts/JointBuildGS:ro" \
    -v "$output_root:/task" \
    -w "/task/runs/$arm" \
    "$roofer_image" \
    --id-attribute stable_id --jobs 1 \
    --box 690791.740 5335864.050 691154.650 5336353.850 \
    "${extra_args[@]}" \
    "/artifacts/JointBuildGS/$classified_rel" \
    "/artifacts/JointBuildGS/$footprint_rel" \
    "/task/runs/$arm" \
    > "$output_root/runs/$arm/roofer.log" 2>&1
  exit_code=$?
  set -e
  runtime_seconds=$((SECONDS - start_seconds))
  printf '{"arm":"%s","exit_code":%d,"runtime_seconds":%d,"scientific_verdict":null}\n' \
    "$arm" "$exit_code" "$runtime_seconds" > "$output_root/runs/$arm/terminal.json"
  if [[ "$exit_code" -ne 0 ]]; then
    echo "Roofer failed for $arm with exit $exit_code" >&2
    exit "$exit_code"
  fi
  docker run --rm --user "$run_user" \
    -v "$repo_root:/workspace/JointBuildGS:ro" \
    -v "$output_root:/task" \
    -w /workspace/JointBuildGS \
    "$tools_image" \
    python scripts/p2/c2_mvs_classification_clip_census_199_v1/analyze.py combine \
      --config "/workspace/JointBuildGS/$config_rel" \
      --output-root /task \
      --arm "$arm"
  docker run --rm --user "$run_user" \
    -v "$output_root:/task" \
    "$tools_image" \
    val3dity "/task/runs/$arm/assembled.city.json" \
      --report "/task/runs/$arm/val3dity_report.json" \
      > "$output_root/runs/$arm/val3dity.log" 2>&1
done

docker run --rm --user "$run_user" \
  -v "$repo_root:/workspace/JointBuildGS:ro" \
  -v "$artifact_root:/artifacts/JointBuildGS:ro" \
  -v "$output_root:/task" \
  -w /workspace/JointBuildGS \
  "$tools_image" \
  python scripts/p2/c2_mvs_classification_clip_census_199_v1/analyze.py finalize \
    --config "/workspace/JointBuildGS/$config_rel" \
    --artifact-root /artifacts/JointBuildGS \
    --output-root /task

echo "$output_root"
