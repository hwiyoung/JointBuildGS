#!/usr/bin/env bash
set -Eeuo pipefail

RUN_ID="20260728_2327"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="configs/input_and_alignment/tum2twin_rv1_20260728_2327.yaml"
REPORT="$REPO/reports/nightly_rv1_${RUN_ID}"
LOCK="$REPORT/nightly.lock"
PID_FILE="$REPORT/nightly.pid"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
HEARTBEAT_PID=""
HEARTBEAT_CONTAINER="jointbuildgs-rv1-heartbeat-${RUN_ID}"
ACTIVE_PID=""
TERMINATING=0

mkdir -p "$REPORT/logs"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "duplicate run rejected: lock is held at $LOCK" >&2
  exit 73
fi

atomic_pid_file() {
  local temporary="${PID_FILE}.tmp.$$"
  printf '%s\n' "$$" > "$temporary"
  mv -f "$temporary" "$PID_FILE"
}

docker_dev() {
  docker run --rm --user "${HOST_UID}:${HOST_GID}" \
    -e MPLCONFIGDIR=/tmp/matplotlib-rv1 \
    -e XDG_CACHE_HOME=/tmp/xdg-rv1 \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    jointbuildgs:dev "$@"
}

docker_p0() {
  docker run --rm --user "${HOST_UID}:${HOST_GID}" \
    -e MPLCONFIGDIR=/tmp/matplotlib-rv1 \
    -e XDG_CACHE_HOME=/tmp/xdg-rv1 \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    jointbuildgs-p0-tools:t0 "$@"
}

mark_failed() {
  local reason="$1"
  echo "nightly R_v1 failed: $reason" >&2
  docker_dev python -m src.rv1_pipeline --config "$CONFIG" --set-stage FAILED --stage-status failed || true
  touch "$REPORT/FAILED"
}

stop_heartbeat() {
  if docker inspect "$HEARTBEAT_CONTAINER" >/dev/null 2>&1; then
    docker stop --time 10 "$HEARTBEAT_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [[ -n "$HEARTBEAT_PID" ]]; then
    wait "$HEARTBEAT_PID" 2>/dev/null || true
  fi
}

graceful_term() {
  TERMINATING=1
  echo "SIGTERM received; forwarding to active stage" >&2
  if [[ -n "$ACTIVE_PID" ]] && kill -0 "$ACTIVE_PID" 2>/dev/null; then
    kill -TERM "$ACTIVE_PID" 2>/dev/null || true
    wait "$ACTIVE_PID" 2>/dev/null || true
  fi
  stop_heartbeat
  mark_failed "graceful SIGTERM"
  exit 143
}

on_exit() {
  local code=$?
  stop_heartbeat
  if [[ $code -ne 0 && $TERMINATING -eq 0 ]]; then
    mark_failed "runner exit code $code"
  fi
}

trap graceful_term TERM INT
trap on_exit EXIT

atomic_pid_file
docker_dev python -m src.rv1_pipeline --config "$CONFIG" --register-background-pid "$$"
docker_dev python -m src.rv1_pipeline --config "$CONFIG" --set-stage N3_FULL_BATCH --stage-status running

docker run --rm --name "$HEARTBEAT_CONTAINER" --user "${HOST_UID}:${HOST_GID}" \
  -e MPLCONFIGDIR=/tmp/matplotlib-rv1 \
  -e XDG_CACHE_HOME=/tmp/xdg-rv1 \
  -v "$REPO:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  jointbuildgs:dev python -m src.rv1_pipeline --config "$CONFIG" --heartbeat-loop &
HEARTBEAT_PID=$!

echo "[$(date --iso-8601=seconds)] N3 cache preparation start"
docker_p0 python scripts/input_and_alignment/tum2twin_rv1/prepare_tum2twin_rv1_cache.py \
  --config "$CONFIG" --all --resume &
ACTIVE_PID=$!
wait "$ACTIVE_PID"
ACTIVE_PID=""

echo "[$(date --iso-8601=seconds)] N3 metric batch start"
docker_dev python -m src.rv1_pipeline \
  --config "$CONFIG" --all --resume &
ACTIVE_PID=$!
wait "$ACTIVE_PID"
ACTIVE_PID=""

stop_heartbeat
HEARTBEAT_PID=""
if [[ ! -f "$REPORT/DONE" ]]; then
  mark_failed "metric process exited without DONE marker"
  exit 1
fi
echo "[$(date --iso-8601=seconds)] DONE"
