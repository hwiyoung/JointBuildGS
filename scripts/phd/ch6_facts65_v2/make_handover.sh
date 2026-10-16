#!/usr/bin/env bash
# PHD-CH6-FACTS65-v2 handover bundle for the document session (same layout as the PHD-CH6-FACTS64-v1 bundle):
# docs (facts table md/json, evidence index, order copy, tables), scripts, evidence copies, the writers' drafts (agents A-D and this
# session M), the results of the three computations of this order (t7_5, t9, t12) and the assembly (final), job lists, logs,
# progress.md, receipt, SHA256SUMS  -> <payload>/handover/PHD-CH6-FACTS65-v2_handover.zip
#   bash make_handover.sh
# Host tools only (cp, rsync, sha256sum, zip). scientific_verdict: null.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/ch6_facts65_v2/PHD-CH6-FACTS65-v2"
H="$P/handover"; B="$H/PHD-CH6-FACTS65-v2"
if [ -d "$B" ]; then mv "$B" "$B.old_$(date +%H%M%S)"; fi
mkdir -p "$B/docs" "$B/scripts" "$B/evidence" "$B/drafts" "$B/results" "$B/jobs" "$B/logs"
cp -r "$REPO/docs/experiments/phd/ch6_facts65_v2/." "$B/docs/"
rsync -a --exclude "__pycache__" "$REPO/scripts/phd/ch6_facts65_v2/" "$B/scripts/"
rsync -a "$P/evidence/" "$B/evidence/"
rsync -a --exclude "__pycache__" "$P/agents/" "$B/drafts/"
for d in t7_5 t9 t12 final; do rsync -a "$P/$d/" "$B/results/$d/"; done
rsync -a "$P/jobs/" "$B/jobs/"
rsync -a "$P/logs/" "$B/logs/"
cp "$P/progress.md" "$P/receipt_task.json" "$B/"
( cd "$B" && find . -type f ! -name SHA256SUMS | sort | xargs -d '\n' sha256sum > SHA256SUMS )
rm -f "$H/PHD-CH6-FACTS65-v2_handover.zip"
( cd "$H" && zip -qr PHD-CH6-FACTS65-v2_handover.zip PHD-CH6-FACTS65-v2 )
rm -rf "$H"/PHD-CH6-FACTS65-v2.old_*
ls -la "$H/PHD-CH6-FACTS65-v2_handover.zip"
sha256sum "$H/PHD-CH6-FACTS65-v2_handover.zip"
echo "files: $(unzip -l "$H/PHD-CH6-FACTS65-v2_handover.zip" | tail -1)"
