#!/usr/bin/env bash
# New output only; frozen source arrays are mounted read-only, without GPU access.
set -euo pipefail
script_dir=$(cd "$(dirname "$0")" && pwd)
repository_root=$(cd "$script_dir/../../.." && pwd)
artifact_root=${1:?Usage: replay_z07_reference_subset.sh ABSOLUTE_ARTIFACT_ROOT NEW_ABSOLUTE_OUTPUT}
task_output=${2:?Usage: replay_z07_reference_subset.sh ABSOLUTE_ARTIFACT_ROOT NEW_ABSOLUTE_OUTPUT}
[[ "$artifact_root" = /* && "$task_output" = /* ]]
mkdir "$task_output"
cp "$script_dir/audit_z07_reference_subset.py" "$task_output/"
cp "$script_dir/replay_z07_reference_subset.sh" "$task_output/"
cp "$repository_root/configs/phd/local_weight_sites_v1/z07_reference_subset_v1.json" "$task_output/config.json"
git -C "$repository_root" rev-parse HEAD > "$task_output/git_commit.txt"
git -C "$repository_root" status --short > "$task_output/git_status.txt"
runtime=(docker run --rm --network none --cpus 2 --memory 4g
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1
  -v "$artifact_root:/art:ro" -v "$task_output:/out"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
  python /out/audit_z07_reference_subset.py --config /out/config.json --output /out/result)
printf '%q ' "${runtime[@]}" > "$task_output/command.txt"
printf '\n' >> "$task_output/command.txt"
"${runtime[@]}" > "$task_output/process.log" 2>&1
