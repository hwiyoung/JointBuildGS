#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
artifact="$(realpath "$repo/../JointBuildGS-artifacts")"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
task="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
reference="$artifact/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run"
raw="$artifact/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz"
output="$task/viewer_rgb_v1"
port=8910
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
if [[ -n "$(ss -H -ltn "sport = :$port")" ]]; then
  printf 'Port %s already occupied; preserving existing service\n' "$port" >&2
  exit 1
fi
for name in jbgs-geogs-rgb-builder-v1 jbgs-geogs-rgb-viewer-8910; do
  if docker container inspect "$name" >/dev/null 2>&1; then
    printf 'Container %s exists; inspect it before a new launch\n' "$name" >&2
    exit 1
  fi
done
test -s "$raw"
test -s "$repo/scripts/phd/geogs_mvs_pgsr_v1/viewer/baselines.py"
test -s "$repo/scripts/phd/geogs_mvs_pgsr_v1/viewer/export_geometry.py"
mkdir -p "$output"
mkdir -p "$output/sources"
source_snapshot="$(mktemp -d "$output/sources/attempt.XXXXXXXX")"
cp -p "$repo/scripts/phd/geogs_mvs_pgsr_v1/viewer/"*.py "$source_snapshot/"
cp -p "$repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$source_snapshot/mvs_depth.py"
cp -p "$repo/configs/phd/geogs_mvs_pgsr_v1/viewer_rgb_v1.json" "$source_snapshot/config.json"
cp -p "${BASH_SOURCE[0]}" "$source_snapshot/start.sh"
git -C "$repo" rev-parse HEAD > "$source_snapshot/operator_head.txt"
sha256sum "$source_snapshot/"*.py "$source_snapshot/config.json" "$source_snapshot/start.sh" > "$source_snapshot/sha256sums.txt"
common=(--read-only --cap-drop ALL --security-opt no-new-privileges --user "$(id -u):$(id -g)"
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  --env MKL_NUM_THREADS=2 --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6)
docker run -d --name jbgs-geogs-rgb-builder-v1 --restart unless-stopped \
  "${common[@]}" --network none --cpus 2 --memory 12g --shm-size 256m \
  --tmpfs /tmp:rw,nosuid,size=256m \
  --mount "type=bind,src=$source_snapshot,dst=/driver,readonly" \
  --mount "type=bind,src=$source_snapshot/config.json,dst=/config.json,readonly" \
  --mount "type=bind,src=$base,dst=/base,readonly" \
  --mount "type=bind,src=$task,dst=/new,readonly" \
  --mount "type=bind,src=$reference,dst=/reference,readonly" \
  --mount "type=bind,src=$raw,dst=/raw/uas.laz,readonly" \
  --mount "type=bind,src=$output,dst=/out" \
  "$image" python /driver/build.py --base /base --new /new --reference /reference \
  --raw-uas /raw/uas.laz --output /out --config /config.json --watch
docker run -d --name jbgs-geogs-rgb-viewer-8910 --restart unless-stopped \
  "${common[@]}" --cpus 1 --memory 512m --publish "127.0.0.1:$port:8080" \
  --mount "type=bind,src=$repo/src/apps/geogs_rgb_comparison_v1,dst=/app,readonly" \
  --mount "type=bind,src=$repo/src/apps/gs3d_4way_viewer/build/three.module.min.js,dst=/vendor/three.module.min.js,readonly" \
  --mount "type=bind,src=$repo/scripts/phd/geogs_mvs_pgsr_v1/viewer/serve.py,dst=/serve.py,readonly" \
  --mount "type=bind,src=$output,dst=/data,readonly" \
  --mount "type=bind,src=$task/evaluation,dst=/results/evaluation,readonly" \
  "$image" python /serve.py
printf 'http://127.0.0.1:%s/\n' "$port"
