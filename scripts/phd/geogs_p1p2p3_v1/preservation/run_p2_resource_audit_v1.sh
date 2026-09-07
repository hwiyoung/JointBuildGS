#!/usr/bin/env bash
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")"
output="$task_root/preservation/after_p2_all_resource_jobs_v1"
resource_root="$task_root/extraction_resource_v3/primary/P2"
queue_root="$task_root/queue_allocator_v2/resource_v3"
conditions=(D005_Pnative D0005_Pnative D0_Pnative D005_Prelease D0005_Prelease D0_Prelease)
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
for condition in "${conditions[@]}"; do
  test -s "$queue_root/done/P2_$condition"
  test -s "$resource_root/$condition/auxiliary_receipt.json"
done
test ! -e "$output"
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
mkdir "$output"
mkdir "$output/code"
cp -p -- "${BASH_SOURCE[0]}" "$output/launcher_snapshot.sh"
for name in audit_p2_resource_jobs_v1.py verify_service_snapshot.py; do
  cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/preservation/$name" "$output/code/$name"
done
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime/audit_first_resource_v3_jobs.py" "$output/code/unchanged_prior_inspector.py"
cp -p -- "$task_root/preservation/services_before.txt" "$output/services_before.txt"
printf '%s\n' "$image" > "$output/image_id.txt"
git -C "$repo_root" rev-parse HEAD > "$output/git_head.txt"
cat > "$output/audit_config.json" <<CONFIG
{
  "task_host_root": "$task_root",
  "specification": {
    "schema": "GEOGS_P2_ALL_RESOURCE_MEMORY_AUDIT_v1", "region": "P2",
    "conditions": ["D005_Pnative", "D0005_Pnative", "D0_Pnative", "D005_Prelease", "D0005_Prelease", "D0_Prelease"],
    "variants": 14, "memory_limit_bytes": 34359738368, "expected_original_services": 62,
    "runtime_image_id": "$image", "scientific_verdict": null,
    "binding": {
      "config_sha256": "b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4",
      "runtime_layout_sha256": "28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5",
      "resource_contract_sha256": "804f371b9db70b089daccdba2052df8c71b54b5d20acba2ea2f5c6d3d7eb7efa",
      "input_manifest_sha256": "6493c602332144510526a54f31700c28cb31eb648250e690d6528fcffe5162a2"
    }
  }
}
CONFIG
trap 'code=$?; printf "%s\n" "$code" > "$output/overall_exit_code.txt"' EXIT
base=(docker run --rm --network none --read-only --cpus 1 --memory 256m --user "$(id -u):$(id -g)"
  --env PYTHONDONTWRITEBYTECODE=1 --mount "type=bind,src=$output/code,dst=/code,readonly"
  --mount "type=bind,src=$output,dst=/out")
resource_command=("${base[@]}")
for condition in "${conditions[@]}"; do
  marker="$queue_root/done/P2_$condition"
  completion_path="$(realpath -- "$(cat "$marker")")"
  [[ "$completion_path" == "$queue_root/claims/P2_$condition"/attempt.*/complete.json ]]
  resource_command+=(--mount "type=bind,src=$marker,dst=/queue_done/P2_$condition,readonly"
    --mount "type=bind,src=$completion_path,dst=/completion/$condition.json,readonly"
    --mount "type=bind,src=$resource_root/$condition/auxiliary_receipt.json,dst=/resource/$condition/auxiliary_receipt.json,readonly")
  variants=(mesh_512 mesh_2048)
  if [[ "$condition" == D005_Pnative ]]; then variants=(anchor_512 anchor mesh_512 mesh_2048); fi
  for variant in "${variants[@]}"; do
    for name in receipt.json memory.jsonl; do
      resource_command+=(--mount "type=bind,src=$resource_root/$condition/auxiliary/$variant/$name,dst=/resource/$condition/auxiliary/$variant/$name,readonly")
    done
  done
done
resource_command+=("$image" python /code/audit_p2_resource_jobs_v1.py --mode resource)
printf '%q ' "${resource_command[@]}" > "$output/resource_command.sh"
printf '\n' >> "$output/resource_command.sh"
if "${resource_command[@]}" > "$output/resource_stdout.log" 2> "$output/resource_stderr.log"; then resource_exit=0; else resource_exit=$?; fi
printf '%s\n' "$resource_exit" > "$output/resource_exit_code.txt"
snapshot=(docker ps -a --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}} {{.Ports}}')
printf '%q ' "${snapshot[@]}" > "$output/service_snapshot_command.sh"
printf '> %q\n' "$output/services_current.txt" >> "$output/service_snapshot_command.sh"
"${snapshot[@]}" > "$output/services_current.txt"
service_command=("${base[@]}" "$image" python /code/verify_service_snapshot.py
  --baseline /out/services_before.txt --current /out/services_current.txt --output /out/service_receipt.json)
printf '%q ' "${service_command[@]}" > "$output/service_command.sh"
printf '\n' >> "$output/service_command.sh"
if "${service_command[@]}" > "$output/service_stdout.log" 2> "$output/service_stderr.log"; then service_exit=0; else service_exit=$?; fi
printf '%s\n' "$service_exit" > "$output/service_exit_code.txt"
final_command=("${base[@]}" "$image" python /code/audit_p2_resource_jobs_v1.py --mode finalize)
printf '%q ' "${final_command[@]}" > "$output/finalize_command.sh"
printf '\n' >> "$output/finalize_command.sh"
"${final_command[@]}" > "$output/finalize_stdout.log" 2> "$output/finalize_stderr.log"
cat "$output/resource_stdout.log" "$output/service_stdout.log" "$output/finalize_stdout.log"
