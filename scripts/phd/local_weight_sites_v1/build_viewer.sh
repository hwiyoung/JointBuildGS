#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "$0")" && pwd)
repository_root=$(cd "$script_dir/../../.." && pwd)
artifact_root=${1:?Usage: build_viewer.sh ABSOLUTE_ARTIFACT_ROOT NEW_ABSOLUTE_OUTPUT}
task_output=${2:?Usage: build_viewer.sh ABSOLUTE_ARTIFACT_ROOT NEW_ABSOLUTE_OUTPUT}
[[ "$artifact_root" = /* && "$task_output" = /* ]]
mkdir "$task_output"
mkdir -p "$task_output/source/src/apps" "$task_output/source/docs/experiments/phd/local_weight_sites_v1"
cp "$script_dir/build_viewer.py" "$script_dir/build_viewer.sh" "$task_output/source/"
cp "$repository_root/scripts/phd/r1r5_comparison_v1/analyze_final_surfaces.py" "$task_output/source/"
cp -r "$repository_root/src/apps/local_weight_sites_v1" "$task_output/source/src/apps/"
cp "$repository_root/docs/experiments/phd/local_weight_sites_v1/CANDIDATE_LEDGER_20260919_ko.md" "$task_output/source/docs/experiments/phd/local_weight_sites_v1/"
cp "$repository_root/configs/phd/local_weight_sites_v1/viewer_v1.json" "$task_output/config.json"
git -C "$repository_root" rev-parse HEAD > "$task_output/git_commit.txt"
git -C "$repository_root" status --short > "$task_output/git_status.txt"
runtime=(docker run --rm --network none --cpus 4 --memory 12g
  -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 -e PYTHONDONTWRITEBYTECODE=1
  -v "$artifact_root:/art:ro" -v "$task_output:/out" -v "$task_output/source:/repo:ro"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
  python /repo/build_viewer.py --config /out/config.json --output /out/site --repository /repo)
printf '%q ' "${runtime[@]}" > "$task_output/command.txt"
printf '\n' >> "$task_output/command.txt"
"${runtime[@]}" > "$task_output/process.log" 2>&1
