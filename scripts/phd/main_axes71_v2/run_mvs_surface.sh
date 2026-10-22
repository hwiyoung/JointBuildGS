#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2 일 1 'MVS 표면': thin runner of mvs_surface.py in jointbuildgs:geogs-conf-guided-v1 (the image of the stage-1 post,
# Open3D 0.19.0), CPU only (no --gpus, CUDA_VISIBLE_DEVICES=""), network off; every input read-only, writes only AX/mvs.
#   [CPUS=16] [MEM=40] bash run_mvs_surface.sh <tag> <check_fuse|build|ranges|prep_tiled|receipt_tiled> <site> [a|b] [...]
#   [SCRIPT=../main_fill_v1/cdgs/tsdf_tiled.py] ... runs another script by its path under scripts/phd/main_axes71_v2 (the tiled TSDF steps)
# python -I with working directory /tmp: no module of a script folder can shadow the standard library (10-22 20:41, numbers.py).
# Mounts: /s0 S0, /s1 S1, /s2 S2, /sb SB, /dr DR (ro); /source = fork r12 (ro, colmap_loader and getWorld2View2); /repo (ro); /w = AX/mvs.
# Log: AX/mvs/logs/<tag>.log (an existing log is renamed first) and a line in AX/mvs/logs/queue.log. scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
AX="$PH/main_axes71_v2/PHD-MAIN-AXES71-v2"; WD="$AX/mvs"
S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S2="$PH/main_stage2_v1/PHD-MAIN-STAGE2-v1"
SB="$PH/main_baselines_v1/PHD-MAIN-BASELINES-v1"; DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
IMG=jointbuildgs:geogs-conf-guided-v1
tag=$1; shift
mkdir -p "$WD/logs"; [ -f "$WD/logs/$tag.log" ] && mv "$WD/logs/$tag.log" "$WD/logs/$tag.$(date +%H%M%S).log"
CPUS=${CPUS:-16}; MEM=${MEM:-40}
t0=$SECONDS
docker run --rm --name "jbgs-ax-mvs-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "$CPUS" --memory "${MEM}g" --memory-swap "${MEM}g" \
  --shm-size 2g -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="$CPUS" -e TZ=Asia/Seoul \
  -e CUDA_VISIBLE_DEVICES="" -e JBGS_IMAGE="$IMG" -e JBGS_IMAGE_ID="$(docker image inspect -f '{{.Id}}' $IMG)" -e JBGS_CPUS="$CPUS" -e JBGS_MEM="${MEM}g" \
  -v "$S0:/s0:ro" -v "$S1:/s1:ro" -v "$S2:/s2:ro" -v "$SB:/sb:ro" -v "$DR:/dr:ro" \
  -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r12:/source:ro" -v "$REPO:/repo:ro" -v "$WD:/w" \
  -w /tmp --entrypoint python "$IMG" -I -u "/repo/scripts/phd/main_axes71_v2/${SCRIPT:-mvs_surface.py}" "$@" > "$WD/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$WD/logs/queue.log"
exit $rc
