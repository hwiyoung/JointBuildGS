#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact="$(realpath "$repo/../JointBuildGS-artifacts")"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parent="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
annotations="$artifact/phase-payloads/phd/manual_region_masks_v1/PHD-P2P3-MANUAL-REGIONS-v1"
task="$artifact/phase-payloads/phd/region_weight_v1/PHD-P2P3-REGION-WEIGHT-v1"
mkdir -p "$task"
bundle="$(mktemp -d "$task/attempt.XXXXXXXX")"
git -C "$repo" rev-parse HEAD > "$bundle/repository_head.txt"
printf '%s\n' "$bundle" > /tmp/jbgs_P2P3_weight_bundle.txt
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --runtime runc --network none --cpus 2 --memory 5g --user "$(id -u):$(id -g)"
 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1
 -v "$repo:/repo:ro" -v "$bundle:/output" -v "$bundle/repository_head.txt:/repository_head.txt:ro"
 -v "$parent/inputs_v2/experiment.json:/parent_config.json:ro" -v "$parent/sources/GeoGS-mvs-pgsr-v1:/parent_source:ro"
 -v "$parent/inputs_v2/P2:/mvs_P2:ro" -v "$parent/inputs_v2/P3:/mvs_P3:ro"
 -v "$annotations/annotation.P2.fur6lKVS/result:/annotations_P2:ro" -v "$annotations/annotation.P3.5CQlJP1P/result:/annotations_P3:ro"
 -v "$base/runs_allocator_v2/P2/D005_Pnative/model/jbgs_complete/iteration_8000:/anchor_P2:ro"
 -v "$base/runs_allocator_v2/P3/D005_Pnative/model/jbgs_complete/iteration_8000:/anchor_P3:ro"
 -v "$parent/evaluation/attempt.LwEnygWG/extractions/P2.mvs.D005_Pnative/receipt.json:/extraction_P2.json:ro"
 -v "$parent/evaluation/attempt.LwEnygWG/extractions/P3.mvs.D005_Pnative/receipt.json:/extraction_P3.json:ro"
 "$image" python /repo/scripts/phd/region_weight_v1/prepare_bundle.py)
printf '%q ' "${command[@]}" > "$bundle/prepare_command.sh"
printf '\n' >> "$bundle/prepare_command.sh"
"${command[@]}" > "$bundle/prepare.log" 2>&1
mkdir "$bundle/app"
cp -p "$repo/src/apps/geogs_rgb_comparison_v1/"{p2p3_weights.html,matched.js,matched.css} "$bundle/app/"
docker run --rm --runtime runc --network none --cpus 2 --memory 3g -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= \
 -e PYTHONDONTWRITEBYTECODE=1 -v "$repo:/repo:ro" -w /repo "$image" python -m unittest \
 tests.phd.test_region_weight_v1 tests.phd.test_p1_single_view_weight_v1 > "$bundle/cpu_tests.log" 2>&1
rg --files "$bundle/scripts" "$bundle/parent_scripts" "$bundle/legacy_scripts" "$bundle/implementation" "$bundle/app" \
 "$bundle/P2/mask" "$bundle/P3/mask" -0 | sort -z | xargs -0 sha256sum > "$bundle/frozen_files.sha256"
sha256sum "$bundle/config.json" "$bundle/P2/config.json" "$bundle/P3/config.json" \
 "$bundle/P2/viewer_config.json" "$bundle/P3/viewer_config.json" "$bundle/source/region_weight_source_provenance.json" >> "$bundle/frozen_files.sha256"
printf '%s\n' "$bundle"
