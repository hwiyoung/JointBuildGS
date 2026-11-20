#!/usr/bin/env bash
# 방법 A: COLMAP 2단계(stereo_fusion), 1단계와 같은 이미지, CPU. 입력은 읽기 전용 마운트 + 심볼릭 링크 작업 폴더.
# run_fusion.sh <name> <mvs workspace 경로(ART 아래 상대)> [threads]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_mvsfilter_v1/PHD-MAIN-MVSFILTER-v1"
name=$1; src=$2; th=${3:-16}
IMG=colmap/colmap@sha256:187ca5ec98e55ed8fbec5f43f9d8f78b7a322b3b7413356634191f7a43c1efcf
WS="$OUT/fusion/$name"; mkdir -p "$WS/stereo" "$OUT/logs"
[[ -e "$WS/images" ]] || ln -s "/art/$src/images" "$WS/images"
[[ -e "$WS/sparse" ]] || ln -s "/art/$src/sparse" "$WS/sparse"
[[ -e "$WS/stereo/depth_maps" ]] || ln -s "/art/$src/stereo/depth_maps" "$WS/stereo/depth_maps"
[[ -e "$WS/stereo/normal_maps" ]] || ln -s "/art/$src/stereo/normal_maps" "$WS/stereo/normal_maps"
[[ -e "$WS/stereo/fusion.cfg" ]] || grep -v '^__auto__' "$ART/$src/stereo/patch-match.cfg" > "$WS/stereo/fusion.cfg"
while (( $(free | awk '/^Mem|^메모리/{printf "%d", ($3)*100/$2}') > 80 )); do echo "host memory > 80 %, waiting"; sleep 60; done
args=(colmap stereo_fusion --workspace_path /ws --workspace_format COLMAP --input_type geometric --output_type PLY --output_path /ws/fused.ply --StereoFusion.num_threads "$th")
printf '%s\n' "${args[@]}" > "$WS/command.txt"
t0=$(date +%s)
set +e
nice -n 19 docker run --rm --network none --runtime runc --name "jbgs-mvsfilter1-fusion-$name" --user "$(id -u):$(id -g)" \
  --cpus "$th" --memory 32g --memory-swap 32g -v "$ART:/art:ro" -v "$WS:/ws:rw" -w /ws \
  --entrypoint nice $IMG -n 19 "${args[@]}" > "$WS/fusion.log" 2>&1
rc=$?
set -e
t1=$(date +%s)
printf '{"task_id":"PHD-MAIN-MVSFILTER-v1","name":"%s","source":"%s","image":"%s","image_id":"%s","exit_code":%d,"seconds":%d,"threads":%s,"scientific_verdict":null}\n' \
  "$name" "$src" "$IMG" "$(docker image inspect -f '{{.Id}}' $IMG)" $rc $((t1-t0)) "$th" > "$WS/fusion_receipt.json"
cat "$WS/fusion_receipt.json"
