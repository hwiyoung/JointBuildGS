#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "$0")" && pwd)
repository_root=$(cd "$script_dir/../../.." && pwd)
task_output=${1:?Usage: publish_viewer.sh ATTEMPT SERVER_DATA NEW_PUBLICATION_NAME}
server_data=${2:?Server data directory required}
publication_name=${3:?Fresh publication name required}
[[ "$task_output" = /* && "$server_data" = /* && "$publication_name" =~ ^[A-Za-z0-9_-]+$ ]]
snapshot="$task_output/application_$publication_name"
mkdir "$snapshot"
cp "$repository_root/src/apps/local_weight_sites_v1/"{index.html,style.css,viewer.js} "$snapshot/"
cp "$script_dir/publish_viewer.py" "$script_dir/publish_viewer.sh" "$snapshot/"
runtime=(docker run --rm --network host --cpus 2 --memory 2g -e PYTHONDONTWRITEBYTECODE=1
  -v "$task_output:/out" -v "$snapshot:/app:ro" -v "$server_data:/publish"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
  python /app/publish_viewer.py --attempt /out --application /app --server-data /publish --name "$publication_name")
printf '%q ' "${runtime[@]}" > "$task_output/${publication_name}_command.txt"
printf '\n' >> "$task_output/${publication_name}_command.txt"
"${runtime[@]}" > "$task_output/${publication_name}_publish.log" 2>&1
