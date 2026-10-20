#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 handover bundle (order 13): the docs folder (reports, number table, order copy, tables, figures with their number
# json, provenance diff), the configuration, the scripts (with the r16 source file), logs, progress.md, the small run records (receipts,
# post host memory, init reports, metrics json without rows, dist json, mechanism json, check comparisons, prep json), SHA256SUMS
# -> <payload>/handover/PHD-MAIN-FIXTEST-v1_handover.zip. Training result files (point clouds, checkpoints, dumps, meshes, per-point npz)
# are not put in; their names and sizes are listed in payload_files.txt.
#   bash make_handover_ft.sh
# Host tools only (cp, rsync, find, sha256sum, zip). scientific_verdict: null.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
H="$P/handover"; B="$H/PHD-MAIN-FIXTEST-v1"
if [ -d "$B" ]; then mv "$B" "$B.old_$(date +%H%M%S)"; fi
mkdir -p "$B/docs" "$B/config" "$B/scripts" "$B/fork_r16" "$B/logs" "$B/payload_tables"
cp -r "$REPO/docs/experiments/phd/main_fixtest_v1/." "$B/docs/"
cp -r "$REPO/configs/phd/main_fixtest_v1/." "$B/config/"
rsync -a --exclude "__pycache__" "$REPO/scripts/phd/main_fixtest_v1/" "$B/scripts/"
cp "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r16/jbgs_judgment.py" "$B/fork_r16/"
rsync -a --exclude "*.npz" --exclude "*.npy" "$P/logs/" "$B/logs/"
cp "$P/progress.md" "$B/"
( cd "$P" && find runs -type f \( -name receipt.json -o -name post_host_memory.json -o -name init_report.json -o -name meta.json -o -name oom_record.json \) \
    -print0 | xargs -0 -r -I{} cp --parents {} "$B/payload_tables/" )
( cd "$P" && find metrics dist mech checks prep tables -maxdepth 3 -type f \( -name '*.json' -o -name '*.md' \) -print0 2>/dev/null \
    | xargs -0 -r -I{} cp --parents {} "$B/payload_tables/" )
( cd "$P" && find runs dist metrics measure -type f \( -name '*.ply' -o -name '*.npz' -o -name '*.npy' -o -name '*.pth' \) -printf '%p\t%s\n' 2>/dev/null | sort ) > "$B/payload_files.txt"
cat > "$B/receipt_task.json" <<JSON
{
 "task": "PHD-MAIN-FIXTEST-v1",
 "branch": "exp/main-experiment",
 "commits": $(git -C "$REPO" log --format='"%h %s"' -- docs/experiments/phd/main_fixtest_v1 scripts/phd/main_fixtest_v1 | head -12 | python3 -c 'import sys,json;print(json.dumps([l.strip().strip(chr(34))[:100] for l in sys.stdin]))'),
 "payload": "PH/main_fixtest_v1/PHD-MAIN-FIXTEST-v1",
 "config_sha256": "$(sha256sum "$REPO/configs/phd/main_fixtest_v1/fixtest_v1.json" | cut -d' ' -f1)",
 "training_result_files_included": false,
 "other_task_folders_touched": false,
 "made": "$(date '+%Y-%m-%d %H:%M:%S %Z')",
 "scientific_verdict": null
}
JSON
( cd "$B" && find . -type f ! -name SHA256SUMS | sort | xargs -d '\n' sha256sum > SHA256SUMS )
rm -f "$H/PHD-MAIN-FIXTEST-v1_handover.zip"
( cd "$H" && zip -qr PHD-MAIN-FIXTEST-v1_handover.zip PHD-MAIN-FIXTEST-v1 )
ls -la "$H/PHD-MAIN-FIXTEST-v1_handover.zip"
sha256sum "$H/PHD-MAIN-FIXTEST-v1_handover.zip"
echo "files: $(unzip -l "$H/PHD-MAIN-FIXTEST-v1_handover.zip" | tail -1)"
