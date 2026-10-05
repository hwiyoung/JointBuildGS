#!/usr/bin/env bash
set -euo pipefail
(( $# == 0 ))
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
art="$(realpath "$repo/../JointBuildGS-artifacts")"
task="$art/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent="$task/main_v2/photometric_walkthrough_v3_2/attempt_20260911T093732Z_WiqKix"
image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
[[ "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" == "$image" ]]
mkdir -p "$task/main_v2/normal_photometry_v3_7"
out="$(mktemp -d "$task/main_v2/normal_photometry_v3_7/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")"
git -C "$repo" rev-parse HEAD > "$out/repository_commit.txt"
command=(docker run --rm --read-only --network none --cpus 4 --memory 4g --memory-swap 4g
 --tmpfs /tmp:rw,size=256m --user "$(id -u):$(id -g)" -w /repo
 -e PYTHONPATH=/repo -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 -e MPLCONFIGDIR=/tmp/mpl
 -e "JBGS_RUNTIME_IMAGE_ID=$image"
 --mount "type=bind,src=$repo,dst=/repo,readonly"
 --mount "type=bind,src=$parent,dst=/parent,readonly"
 --mount "type=bind,src=$art/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs,dst=/inputs,readonly"
 --mount "type=bind,src=$out,dst=/output"
 --entrypoint python "$image" -m scripts.phd.local_complementary_refinement_v1.normal_photometry_v3_7
 --parent /parent --inputs /inputs --config /repo/configs/phd/local_complementary_refinement_v1/normal_photometry_v3_7.json --output /output)
printf '%q ' "${command[@]}" > "$out/command.sh"
printf '\n' >> "$out/command.sh"
printf '%s\n' "$out"
"${command[@]}" > "$out/execute.log" 2>&1
cat "$out/execute.log"
