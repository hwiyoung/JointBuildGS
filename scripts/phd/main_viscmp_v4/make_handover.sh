#!/usr/bin/env bash
# PHD-MAIN-VISCMP-v4 handover zips (request 8): docs (report, request, numbers, tables, figures png/pdf/json), configs, the config lock,
# scripts, logs, prep and first-viewer records, SHA256SUMS. No point cloud, mesh or original photo.
#   full  : PHD-MAIN-VISCMP-v4_handover.zip
#   light : PHD-MAIN-VISCMP-v4_handover_light.zip (every png -> JPEG quality 92 with the same pixels, no pdf)
#   bash make_handover.sh -> PH/main_viscmp_v4/PHD-MAIN-VISCMP-v4/handover/
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
VC="$ART/phase-payloads/phd/main_viscmp_v4/PHD-MAIN-VISCMP-v4"; OUT="$VC/handover"; N=PHD-MAIN-VISCMP-v4
stage() {   # $1 = stage dir
  local ST="$1/$N"
  rm -rf "$1"; mkdir -p "$ST/configs" "$ST/scripts" "$ST/payload_records/prep" "$ST/payload_records/logs" "$ST/payload_records/work"
  cp -r "$REPO/docs/experiments/phd/main_viscmp_v4" "$ST/docs"
  cp "$REPO/configs/phd/main_viscmp_v4/"*.json "$ST/configs/"
  cp "$REPO/scripts/phd/main_viscmp_v4/"*.py "$REPO/scripts/phd/main_viscmp_v4/"*.sh "$ST/scripts/"
  cp "$VC/config_lock.json" "$ST/payload_records/"; cp "$VC/prep/"*.json "$ST/payload_records/prep/"; cp "$VC/logs/"*.log "$ST/payload_records/logs/"
  cp "$VC/work/firstview.json" "$VC/work/"blind_*.png "$VC/work/v5_excl_photo.png" "$ST/payload_records/work/"
  for s in B0_b10 B173nb_b10 R1rep_b10; do cp "$VC/work/split_$s.json" "$ST/payload_records/work/"; done
}
sums() { (cd "$1/$N" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS); }
mkdir -p "$OUT"
stage "$OUT/stage"; sums "$OUT/stage"
rm -f "$OUT/${N}_handover.zip"; (cd "$OUT/stage" && zip -qr "$OUT/${N}_handover.zip" "$N"); rm -rf "$OUT/stage"
stage "$OUT/stage_light"
find "$OUT/stage_light/$N" -name "*.pdf" -delete
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$OUT/stage_light:/s" --entrypoint python jointbuildgs:dev -c "
from pathlib import Path
from PIL import Image
for p in Path('/s').rglob('*.png'):
    im = Image.open(p).convert('RGB'); im.save(p.with_suffix('.jpg'), quality=92); p.unlink()
"
grep -rl --include=*.md --include=*.json '\.png' "$OUT/stage_light/$N" | xargs -r sed -i 's/\.png/.jpg/g'
sums "$OUT/stage_light"
rm -f "$OUT/${N}_handover_light.zip"; (cd "$OUT/stage_light" && zip -qr "$OUT/${N}_handover_light.zip" "$N"); rm -rf "$OUT/stage_light"
ls -la "$OUT/"*.zip; sha256sum "$OUT/"*.zip
