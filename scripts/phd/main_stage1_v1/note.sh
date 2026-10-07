#!/usr/bin/env bash
# PHD-MAIN-STAGE1-v1: append one line to progress.md under the same lock the training watcher uses.   bash note.sh "<text>"
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1
exec 8>>"$OUT/logs/progress.lock"; flock 8
printf -- "- %s %s\n" "$(date +%H:%M)" "$1" >> "$OUT/progress.md"
