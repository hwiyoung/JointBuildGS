#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 ))
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
art="$(realpath "$repo/../JointBuildGS-artifacts")"
task="$art/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
attempt="$(realpath "$1")"
[[ "$attempt" == "$task/main_v2/normal_photometry_v3_7/attempt_"* ]]
root="$(mktemp -d "$task/main_v2/normal_photometry_v3_7/evaluation_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")"
mkdir "$root/payload"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --read-only --network none --cpus 2 --memory 3g --memory-swap 3g --tmpfs /tmp:rw,size=128m
 --user "$(id -u):$(id -g)" -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1 -e "JBGS_RUNTIME_IMAGE_ID=$image"
 --mount "type=bind,src=$attempt,dst=/attempt,readonly"
 --mount "type=bind,src=$art/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/da3_refinement_spatial_v1,dst=/paired,readonly"
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/evaluate_normal_photometry_v3_7.py,dst=/audit.py,readonly"
 --mount "type=bind,src=$root/payload,dst=/evaluation"
 --entrypoint python "$image" /audit.py --attempt /attempt --paired /paired --output /evaluation)
cp "${BASH_SOURCE[0]}" "$root/"
git -C "$repo" rev-parse HEAD > "$root/repository_commit.txt"
printf '%q ' "${command[@]}" > "$root/command.sh"
printf '\n' >> "$root/command.sh"
printf '%s\n' "$root"
"${command[@]}" > "$root/execute.log" 2>&1
cat "$root/execute.log"
