#!/usr/bin/env bash
# PHD-CH6-FACTS64-v1 handover bundle for the document session (same layout as the PHD-CH6-SUPPORT-v1 bundle):
# docs (facts table md/json, Figure 6.1 v3, site tables, evidence index), scripts, evidence copies (configs, report sections,
# payload records named in the facts), the fact drafts of the four writers (agents A, B, C and this session M), task results
# (t7 site tables, t8 counts), job lists, logs, progress.md, receipt, SHA256SUMS
#   -> <payload>/handover/PHD-CH6-FACTS64-v1_handover.zip
#   bash make_handover.sh
# Host tools only (cp, rsync, sha256sum, zip). scientific_verdict: null.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/ch6_facts64_v1/PHD-CH6-FACTS64-v1"
H="$P/handover"; B="$H/PHD-CH6-FACTS64-v1"
if [ -d "$B" ]; then mv "$B" "$B.old_$(date +%H%M%S)"; fi
mkdir -p "$B/docs" "$B/scripts" "$B/evidence" "$B/drafts" "$B/results/t7" "$B/results/t8" "$B/jobs" "$B/logs"
cp -r "$REPO/docs/experiments/phd/ch6_facts64_v1/." "$B/docs/"
rsync -a --exclude "__pycache__" "$REPO/scripts/phd/ch6_facts64_v1/" "$B/scripts/"
rsync -a "$P/evidence/" "$B/evidence/"
rsync -a "$P/agents/" "$B/drafts/"
cp "$P/t7/"{sites.csv,sites.json,sites_stats.json,undecidable_faces.csv} "$B/results/t7/"
cp "$P/t8/"{b0_walls.json,b0_walls.md} "$B/results/t8/"
rsync -a "$P/final/" "$B/results/final/"
rsync -a "$P/jobs/" "$B/jobs/"
rsync -a "$P/logs/" "$B/logs/"
cp "$P/progress.md" "$P/receipt_task.json" "$B/"
( cd "$B" && find . -type f ! -name SHA256SUMS | sort | xargs -d '\n' sha256sum > SHA256SUMS )
rm -f "$H/PHD-CH6-FACTS64-v1_handover.zip"
( cd "$H" && zip -qr PHD-CH6-FACTS64-v1_handover.zip PHD-CH6-FACTS64-v1 )
ls -la "$H/PHD-CH6-FACTS64-v1_handover.zip"
sha256sum "$H/PHD-CH6-FACTS64-v1_handover.zip"
echo "files: $(unzip -l "$H/PHD-CH6-FACTS64-v1_handover.zip" | tail -1)"
