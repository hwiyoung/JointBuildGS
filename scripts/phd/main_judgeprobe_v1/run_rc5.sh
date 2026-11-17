#!/usr/bin/env bash
# 다시 셀 것 5 실행기: JC 결과를 /out(읽기 전용)로, 그림은 우리 결과 폴더의 rc5_stage 로.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
JC="$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2"; OUT="$ART/phase-payloads/phd/main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1"
mkdir -p "$OUT/rc5_stage/figures" "$OUT/rc5_stage/mpl" "$OUT/logs"
nice -n 19 docker run --rm --read-only --network none --runtime runc -e CUDA_VISIBLE_DEVICES= --name jbgs-judgeprobe1-rc5 --user "$(id -u):$(id -g)" \
  --cpus 4 --memory 32g --memory-swap 32g --shm-size 2g --tmpfs /tmp:size=4g -e TMPDIR=/tmp -e MPLCONFIGDIR=/docs/mpl -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e TZ=Asia/Seoul \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$JC:/out:ro" -v "$REPO/configs/phd/main_judgecheck_v2:/cfg:ro" -v "$OUT/rc5_stage:/docs:rw" -v /usr/share/fonts/opentype/noto:/fonts:ro -w /tmp \
  --entrypoint nice jointbuildgs:dev -n 19 python -B -u /repo/scripts/phd/main_judgeprobe_v1/p8_rc5.py 2>&1 | tee "$OUT/logs/rc5_$(date -u +%Y%m%dT%H%M%SZ).log"
