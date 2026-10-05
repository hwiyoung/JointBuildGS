#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
art=$(realpath -e "$repo/../JointBuildGS-artifacts")
root="$art/phase-payloads/phd/irregular_source_masks_v1/PHD-IRREGULAR-SOURCE-MASKS-v1"
mkdir -p "$root"
attempt=$(mktemp -d "$root/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
mkdir -p "$attempt/source_snapshot" "$attempt/report"
cd "$repo"
files=(AGENTS.md src/phd/irregular_source_masks_v1.py src/phd/mvs_evidence_v1.py src/phd/mvs_surface_update_v1.py
  src/phd/geogs_mvs_pgsr_v1/mvs_depth.py scripts/phd/mvs_evidence_v1/build.py
  src/apps/mvs_evidence_v1/index.html tests/phd/test_mvs_evidence_v1.py
  tests/phd/test_mvs_evidence_driver_v1.py tests/phd/test_irregular_source_masks_v1.py
  configs/phd/irregular_source_masks_v1/experiment.json)
cp --parents "${files[@]}" "$attempt/source_snapshot/"
cp -r --parents scripts/phd/irregular_source_masks_v1 src/apps/irregular_source_masks_v1 "$attempt/source_snapshot/"
cp src/apps/irregular_source_masks_v1/index.html "$attempt/report/index.html"
git rev-parse HEAD > "$attempt/git_base.txt"
date -u +%FT%TZ > "$attempt/launched_utc.txt"
printf '%s\n' "$attempt" > "$attempt/host_output.txt"
printf 'PREPARING · 비정형 마스크의 원픽셀별 관측 검사 준비\n' > "$attempt/status.txt"
(
  cd "$attempt/source_snapshot"
  find . -type f -print0 | sort -z | xargs -0 sha256sum > "$attempt/source_sha256.txt"
)
unit="jbgs-irregular-masks-$(basename "$attempt" | tr '[:upper:]' '[:lower:]')"
printf '%s\n' "$unit" > "$attempt/systemd_unit.txt"
systemd-run --user --unit "$unit" --property=Type=exec \
  --property="StandardOutput=append:$attempt/run.log" \
  --property="StandardError=append:$attempt/run.log" \
  /bin/bash "$attempt/source_snapshot/scripts/phd/irregular_source_masks_v1/run_worker.sh" "$repo" "$attempt"
printf '%s\n' "$attempt"
