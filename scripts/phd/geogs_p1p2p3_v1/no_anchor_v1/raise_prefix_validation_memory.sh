#!/usr/bin/env bash
# One recorded resource amendment for the already running, CPU-only 8k validator.
set -euo pipefail
prefix_rm_region="${1:?P1 or P3}"
case "$prefix_rm_region" in P1|P3) ;; *) exit 2 ;; esac
prefix_rm_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
prefix_rm_task=$(realpath "$prefix_rm_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
prefix_rm_container="jbgs-geogs-prefix8000-$prefix_rm_region-validate"
prefix_rm_out="$prefix_rm_task/completed_prefix8000_v1/$prefix_rm_region/validation/resource_memory_amendment_v1"
test ! -e "$prefix_rm_out"
test "$(docker inspect "$prefix_rm_container" --format '{{.State.Running}} {{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.Image}}')" = 'true 2147483648 2147483648 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
test "$(docker inspect "$prefix_rm_container" --format '{{json .Config.Cmd}}')" = "[\"/opt/geogs/bin/python\",\"/prefix/validate.py\",\"--region\",\"$prefix_rm_region\"]"
test "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)" -ge 25165824
mkdir -p -- "$prefix_rm_out"
cp -- "${BASH_SOURCE[0]}" "$prefix_rm_out/launcher.sh"
trap 'prefix_rm_exit=$?; printf "%s\n" "$prefix_rm_exit" > "$prefix_rm_out/exit_code.txt"' EXIT
docker inspect "$prefix_rm_container" > "$prefix_rm_out/docker_before.json"
docker exec "$prefix_rm_container" cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.pressure > "$prefix_rm_out/cgroup_before.txt"
date -u +%FT%TZ > "$prefix_rm_out/started_utc.txt"
cat > "$prefix_rm_out/amendment.json" <<JSON
{"schema":"GEOGS_PREFIX_VALIDATION_RESOURCE_AMENDMENT_v1","scientific_verdict":null,"region":"$prefix_rm_region","container":"$prefix_rm_container","old_memory_bytes":2147483648,"new_memory_bytes":8589934592,"new_memory_swap_total_bytes":8589934592,"cpu_limit_unchanged":true,"validation_logic_and_input_bytes_changed":false,"training_or_export_modified":false,"reason":"Observed cgroup current near2GiB with sustained full memory pressure during immutable mmap checkpoint/PLY verification; permit file working set to remain resident.","original_command_resource_limit_preserved_in_driver_snapshot":true}
JSON
docker update --memory 8g --memory-swap 8g "$prefix_rm_container" > "$prefix_rm_out/docker_update.log"
docker inspect "$prefix_rm_container" > "$prefix_rm_out/docker_after.json"
test "$(docker inspect "$prefix_rm_container" --format '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}')" = '8589934592 8589934592'
docker exec "$prefix_rm_container" cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.pressure > "$prefix_rm_out/cgroup_after.txt"
date -u +%FT%TZ > "$prefix_rm_out/finished_utc.txt"
sha256sum "$prefix_rm_out/launcher.sh" "$prefix_rm_out/amendment.json" "$prefix_rm_out/docker_before.json" "$prefix_rm_out/docker_after.json" > "$prefix_rm_out/SHA256SUMS"
printf '%s\n' "$prefix_rm_region CPU validator memory changed2GiB→8GiB; validation logic and GPU jobs unchanged"
