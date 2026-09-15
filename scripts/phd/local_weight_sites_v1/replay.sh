#!/usr/bin/env bash
# Reproduce the CPU diagnostic in a new output directory; no GPU or training.
set -euo pipefail
script_dir=$(cd "$(dirname "$0")" && pwd)
repository_root=$(cd "$script_dir/../../.." && pwd)
artifact_root=${1:?Usage: replay.sh ABSOLUTE_ARTIFACT_ROOT NEW_ABSOLUTE_OUTPUT_DIRECTORY}
task_output=${2:?Usage: replay.sh ABSOLUTE_ARTIFACT_ROOT NEW_ABSOLUTE_OUTPUT_DIRECTORY}
[[ "$artifact_root" = /* && "$task_output" = /* ]]
mkdir "$task_output"
mkdir "$task_output/source"
cp "$script_dir/search.py" "$script_dir/inspect_sites.py" "$script_dir/finalize.py" "$task_output/source/"
cp "$repository_root/scripts/phd/r1r5_comparison_v1/analyze_final_surfaces.py" "$task_output/source/"
cp "$repository_root/configs/phd/local_weight_sites_v1/search_v1.json" "$task_output/config.json"
cp "$repository_root/configs/phd/local_weight_sites_v1/review_v1.json" "$task_output/review_config.json"
git -C "$repository_root" rev-parse HEAD > "$task_output/git_commit.txt"
git -C "$repository_root" status --short > "$task_output/git_status.txt"
runtime=(docker run --rm --network none --cpus 4 --memory 12g
  -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 -e PYTHONDONTWRITEBYTECODE=1
  -v "$artifact_root:/art:ro" -v "$task_output:/out" -v "$task_output/source:/source:ro"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e)
"${runtime[@]}" python /source/search.py --config /out/config.json --output /out/result > "$task_output/search.log" 2>&1
"${runtime[@]}" python /source/inspect_sites.py --attempt /out --ids W138 W145 W139 W125 W013 W015 W019 W020 W011 W150 > "$task_output/inspect.log" 2>&1
"${runtime[@]}" python /source/finalize.py --attempt /out --review /out/review_config.json > "$task_output/finalize.log" 2>&1
