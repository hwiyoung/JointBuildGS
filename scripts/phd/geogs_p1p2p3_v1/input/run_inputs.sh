#!/usr/bin/env bash
# New-only input preparation with stage-specific read-only mounts; never mounts UAS.
set -euo pipefail
REGION="${1:?region P1/P2/P3 required}"
STAGE="${2:?stage cameras/surface required}"
case "$REGION" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$STAGE" in cameras|surface) ;; *) exit 2 ;; esac
REPO_ROOT="$(git rev-parse --show-toplevel)"
ARTIFACT_HOST="$(realpath "$REPO_ROOT/../JointBuildGS-artifacts")"
ARTIFACT_CANON=/artifacts/JointBuildGS
TASK_REL=phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1
REGION_REL="$TASK_REL/inputs/$REGION"
IMAGE_ID=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
LOG_ROOT="$ARTIFACT_HOST/$TASK_REL/input_logs"
mkdir -p "$ARTIFACT_HOST/$REGION_REL" "$LOG_ROOT"
DEST=scene
if [ "$STAGE" = surface ]; then DEST=surface; fi
if [ -e "$ARTIFACT_HOST/$REGION_REL/$DEST" ] || [ -e "$LOG_ROOT/${REGION}_${STAGE}.command" ]; then
  printf '%s\n' 'Refusing to overwrite an existing input stage or receipt' >&2
  exit 3
fi
DOCKER_ARGS=(docker run --rm --network none --read-only --tmpfs /tmp:rw,size=512m
  --user "$(id -u):$(id -g)" --cpus 4 --memory 8g -w /workspace
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4
  -e "JBGS_SOURCE_GIT_HEAD=$(git rev-parse HEAD)" -e "JBGS_CONTAINER_IMAGE_ID=$IMAGE_ID"
  --mount "type=bind,src=$REPO_ROOT,dst=/workspace,readonly"
  --mount "type=bind,src=$ARTIFACT_HOST/$REGION_REL,dst=$ARTIFACT_CANON/$REGION_REL")
test ! -e "$LOG_ROOT/${REGION}_${STAGE}.config.json"
cp --no-clobber "$REPO_ROOT/configs/phd/geogs_p1p2p3_v1/experiment_v1.json" "$LOG_ROOT/${REGION}_${STAGE}.config.json"
DOCKER_ARGS+=(--mount "type=bind,src=$LOG_ROOT/${REGION}_${STAGE}.config.json,dst=/stage_config.json,readonly")
if [ "$STAGE" = cameras ]; then
  VIEW_REL="phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-$REGION-INPUT-v5/run/common/views.json"
  CAMERA_REL=phase-payloads/p0-audit/data/work/mvs/colmap_dense
  DOCKER_ARGS+=(--mount "type=bind,src=$ARTIFACT_HOST/$VIEW_REL,dst=$ARTIFACT_CANON/$VIEW_REL,readonly"
    --mount "type=bind,src=$ARTIFACT_HOST/$CAMERA_REL,dst=$ARTIFACT_CANON/$CAMERA_REL,readonly")
else
  ACQ_REL="phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-$REGION-ACQUISITION-v4/run/acquisition.npz"
  if [ "$REGION" = P3 ]; then
    ACQ_REL=phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-P3-ACQUISITION-ADAPTER-v5/run/acquisition.npz
  fi
  DOCKER_ARGS+=(--mount "type=bind,src=$ARTIFACT_HOST/$ACQ_REL,dst=$ARTIFACT_CANON/$ACQ_REL,readonly")
fi
DOCKER_ARGS+=(--entrypoint python "$IMAGE_ID" -m scripts.phd.geogs_p1p2p3_v1.input.prepare
  --config /stage_config.json --region "$REGION" --stage "$STAGE"
  --output "$ARTIFACT_CANON/$REGION_REL/$DEST")
(set -o noclobber; printf '%q ' "${DOCKER_ARGS[@]}" > "$LOG_ROOT/${REGION}_${STAGE}.command")
set +e
"${DOCKER_ARGS[@]}" > "$LOG_ROOT/${REGION}_${STAGE}.log" 2>&1
STAGE_EXIT=$?
set -e
(set -o noclobber; printf '%s\n' "$STAGE_EXIT" > "$LOG_ROOT/${REGION}_${STAGE}.exit")
if [ -d "$ARTIFACT_HOST/$REGION_REL/$DEST" ]; then
  cp --no-clobber "$LOG_ROOT/${REGION}_${STAGE}.config.json" "$ARTIFACT_HOST/$REGION_REL/$DEST/run_config_snapshot.json"
fi
tail -n 8 "$LOG_ROOT/${REGION}_${STAGE}.log"
exit "$STAGE_EXIT"
