#!/usr/bin/env bash
set -euo pipefail
repo=${1:?source checkout}; attempt=${2:?new immutable attempt}
art=$(realpath -e "$repo/../JointBuildGS-artifacts")
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
name="jbgs-irregular-$(basename "$attempt" | tr '[:upper:]' '[:lower:]')"
printf '%s\n' "$name" > "$attempt/container_name.txt"
failure(){ code=$?; if ((code != 0)); then printf 'FAILED · 원픽셀 마스크 계산 실패 (exit %s). run.log와 부분 결과를 확인하세요.\n' "$code" > "$attempt/status.txt"; printf '{"status":"FAILED","exit_code":%s,"scientific_verdict":null}\n' "$code" > "$attempt/failure.json"; fi; }
trap failure EXIT
cd "$attempt/source_snapshot"
sha256sum --check --quiet "$attempt/source_sha256.txt"
docker run --name "$name" --network none --cpus 4 --memory 16g --memory-swap 16g \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint /opt/geogs/bin/python -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MPLCONFIGDIR=/tmp/mpl \
  -e JBGS_RUNTIME_IMAGE_ID="$image" \
  -e JBGS_GIT_COMMIT="$(cat "$attempt/git_base.txt")" \
  -v "$attempt/source_snapshot:/repo:ro" \
  -v "$art/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs:/inputs:ro" \
  -v "$art/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/contracts/execution_v1.json:/base_config.json:ro" \
  -v "$art/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2:/mvs:ro" \
  -v "$art/phase-payloads/phd/mvs_evidence_v1/PHD-MVS-EVIDENCE-v1/attempt_20260914T144906Z_OBsE9y/evidence:/parent:ro" \
  -v "$attempt:/out" -w /repo "$image" \
  scripts/phd/irregular_source_masks_v1/validate_and_build.py \
  --config /repo/configs/phd/irregular_source_masks_v1/experiment.json \
  --inputs /inputs --mvs /mvs --parent /parent --output /out/evidence
docker inspect --format '{{json .State}}' "$name" > "$attempt/container_exit.json"
