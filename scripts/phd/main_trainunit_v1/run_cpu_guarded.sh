#!/usr/bin/env bash
# run_cpu.sh with a host-memory guard (after the 2026-11-12 15:05 host lockup): every 5 s, if host MemAvailable falls
# below the floor, this task's container is killed first so the shared host does not lock up. Nothing else is touched.
#   bash run_cpu_guarded.sh <floor_GB> <tag> <cpus> <memory> <script.py> [args...]
set -u
floor=$1; shift
tag=$1
here=$(cd "$(dirname "$0")" && pwd)
bash "$here/run_cpu.sh" "$@" &
pid=$!
while kill -0 $pid 2>/dev/null; do
  avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
  if [ "$avail" -lt "$floor" ]; then
    docker kill "jbgs-trainunit-$tag" >/dev/null 2>&1
    echo "- $(date -Iseconds): 메모리 보호: 호스트 가용 ${avail} GB < ${floor} GB → 이 작업 컨테이너 jbgs-trainunit-$tag 멈춤(다른 작업은 건드리지 않음)." \
      >> "$here/../../../docs/experiments/phd/main_trainunit_v1/issues.md"
    break
  fi
  sleep 5
done
wait $pid
