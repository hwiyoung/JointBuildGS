#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1"
PH="$ART/phase-payloads/phd"
IMG=${IMG:-jointbuildgs:dev}
MEM=${MEM:-16}
CPUS=${CPUS:-4}
tag=$1; shift
mkdir -p "$OUT/logs" "$OUT/tmp" "$OUT/locks" "$REPO/configs/phd/main_target_v1" "$REPO/docs/experiments/phd/main_target_v1"
exec 9>"$OUT/locks/${TARGET_LANE:-stage0}.lock"
flock -x 9
nice -n 19 docker run --rm --read-only --network none --runtime runc \
  --name "jbgs-target-$tag" --user "$(id -u):$(id -g)" --cpus "$CPUS" --memory "${MEM}g" --memory-swap "${MEM}g" \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache \
  -e TZ=Asia/Seoul -e TARGET_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO" rev-parse HEAD)" \
  -e TARGET_IMAGE="$(docker image inspect -f '{{.Id}}' "$IMG")" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$PH:/ph:ro" -v "$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1:/s0:ro" \
  -v "$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1:/s1:ro" \
  -v "$PH/main_stage2_v1/PHD-MAIN-STAGE2-v1:/s2:ro" \
  -v "$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1:/dr:ro" \
  -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r12:/source:ro" \
  -v "$REPO/configs/phd/main_target_v1:/cfg:rw" \
  -v "$REPO/docs/experiments/phd/main_target_v1:/docs:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint nice "$IMG" -n 19 python -B -u \
  "/repo/scripts/phd/main_target_v1/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
