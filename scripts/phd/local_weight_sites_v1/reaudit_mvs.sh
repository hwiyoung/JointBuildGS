#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "$0")" && pwd)
repository_root=$(cd "$script_dir/../../.." && pwd)
artifact_root=${1:?Absolute artifact root required}
task_output=${2:?Fresh absolute output required}
[[ "$artifact_root" = /* && "$task_output" = /* ]]
mkdir "$task_output"
mkdir -p "$task_output/source/src/apps"
cp "$script_dir/"reaudit_mvs.{py,sh} "$task_output/source/"
cp -r "$repository_root/src/apps/local_weight_sites_v1" "$task_output/source/src/apps/"
cp "$repository_root/configs/phd/local_weight_sites_v1/viewer_v1.json" "$task_output/source/"
cp "$repository_root/configs/phd/local_weight_sites_v1/mvs_reaudit_v1.json" "$task_output/config.json"
cp "$repository_root/docs/experiments/phd/local_weight_sites_v1/CANDIDATE_LEDGER_20260919_ko.md" "$task_output/source/candidate_ledger.md"
cp "$repository_root/docs/experiments/phd/local_weight_sites_v1/MVS_REAUDIT_20260921_ko.md" "$task_output/source/mvs_reaudit_report.md"
git -C "$repository_root" rev-parse HEAD > "$task_output/git_commit.txt"
git -C "$repository_root" status --short > "$task_output/git_status.txt"
runtime=(docker run --rm --network none --cpus 2 --memory 8g
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1
  -v "$artifact_root:/art:ro" -v "$task_output:/out" -v "$task_output/source:/repo:ro"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
  python /repo/reaudit_mvs.py --config /out/config.json --art /art --output /out/site --repository /repo)
printf '%q ' "${runtime[@]}" > "$task_output/command.txt"
printf '\n' >> "$task_output/command.txt"
"${runtime[@]}" > "$task_output/process.log" 2>&1
