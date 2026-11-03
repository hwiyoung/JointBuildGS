#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
for key in B173nb_b10__ALS__baseline_30000 B173nb_b10__LoD2__GeoGS_30000 B173nb_b10__ALS__GeoGS_30000 B173nb_b10__LoD2__2DGS_30000 B173nb_b10__LoD2__CDGS_30000 B173nb_b10__ALS__CDGS_30000; do
 bash "$REPO/scripts/phd/main_rescore_v1/run_gpu.sh" "jobs/$key.json"
done
