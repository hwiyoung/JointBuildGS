#!/usr/bin/env bash
# PHD-MAIN-UNCERT-v1 thin runner of one CPU step (network off, no GPU, CUDA_VISIBLE_DEVICES=""; nice 19). Every input read-only except
# this payload (/out) and, for the steps that write the repository's docs, /docs = docs/experiments/phd/main_uncert_v1.
#   [CPUS=16] [MEM=40] [IMG=jointbuildgs:dev] bash run_cpu_uc.sh <tag> <script.py> [args ...]
# IMG=jointbuildgs:geogs-conf-guided-v1 for the MVS point step (it imports the fork's colmap_loader through the AXES71 mvs_surface.py).
# Mounts: /ph = phase-payloads/phd (ro), /out = PH/main_uncert_v1/PHD-MAIN-UNCERT-v1 (rw), /s0 /s1 /s2 /dr (ro, the mount names of
# scripts/phd/main_axes71_v2/mvs_surface.py), /art = JointBuildGS-artifacts (ro), /source = fork r12 (ro), /repo (ro), /docs (rw), fonts.
# python -I, working directory /tmp (no script folder can shadow the standard library). Log: /out/logs/<tag>.log (an existing log is
# renamed first) and a line in /out/logs/queue.log. scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
OUT="$PH/main_uncert_v1/PHD-MAIN-UNCERT-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"
S2="$PH/main_stage2_v1/PHD-MAIN-STAGE2-v1"; DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
DOCS="$REPO/docs/experiments/phd/main_uncert_v1"
IMG=${IMG:-jointbuildgs:dev}
tag=$1; shift; script=$1; shift
mkdir -p "$OUT/logs" "$DOCS"; [ -f "$OUT/logs/$tag.log" ] && mv "$OUT/logs/$tag.log" "$OUT/logs/$tag.$(date +%H%M%S).log"
CPUS=${CPUS:-16}; MEM=${MEM:-40}
t0=$SECONDS
nice -n 19 docker run --rm --name "jbgs-uc-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "$CPUS" --memory "${MEM}g" \
  --memory-swap "${MEM}g" --shm-size 4g -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e TZ=Asia/Seoul -e CUDA_VISIBLE_DEVICES="" -e UC_CPUS="$CPUS" \
  -e UC_MEM="${MEM}g" -e UC_IMAGE="$IMG" -e UC_IMAGE_ID="$(docker image inspect -f '{{.Id}}' "$IMG")" \
  -v "$PH:/ph:ro" -v "$OUT:/out" -v "$S0:/s0:ro" -v "$S1:/s1:ro" -v "$S2:/s2:ro" -v "$DR:/dr:ro" -v "$ART:/art:ro" \
  -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r12:/source:ro" -v "$REPO:/repo:ro" -v "$DOCS:/docs" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /tmp --entrypoint python "$IMG" -I -u "/repo/scripts/phd/main_uncert_v1/$script" "$@" > "$OUT/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$OUT/logs/queue.log"
exit $rc
