#!/usr/bin/env bash
# Read-only host metadata; no service control or project dependencies on the host.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
label=${1:?unique environment snapshot label}
[[ $label =~ ^[a-zA-Z0-9_-]+$ ]]
output="$task_root/main_v2/environment/$label"
[[ ! -e $output ]]
mkdir -p "$output"
date --iso-8601=seconds > "$output/time.txt"
git -C "$repo" rev-parse HEAD > "$output/repository_commit.txt"
git -C "$repo" status --porcelain=v1 > "$output/repository_status.txt"
docker ps --format '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}' > "$output/containers.tsv"
docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}' > "$output/runtime_image.txt"
nvidia-smi --query-gpu=index,name,uuid,memory.total,memory.used,memory.free,utilization.gpu --format=csv > "$output/gpus.csv"
nvidia-smi --query-compute-apps=pid,process_name,gpu_uuid,used_gpu_memory --format=csv > "$output/compute_apps.csv"
cat /proc/meminfo > "$output/meminfo.txt"
cat /proc/loadavg > "$output/loadavg.txt"
df -B1 "$task_root" /var/lib/docker > "$output/disk.txt"
sha256sum "$repo/configs/phd/local_complementary_refinement_v1/experiment_v2.json" > "$output/config_sha256.txt"
