#!/usr/bin/env bash
set -euo pipefail
REGION="${1:?region required}"
STAGE="${2:?initialization or depth required}"
case "$REGION" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$STAGE" in initialization|depth) ;; *) exit 2 ;; esac
REPO_ROOT="$(git rev-parse --show-toplevel)"
ARTIFACT_HOST="$(realpath "$REPO_ROOT/../JointBuildGS-artifacts")"
TASK_REL=phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1
REGION_REL="$TASK_REL/inputs/$REGION"
ARTIFACT_CANON=/artifacts/JointBuildGS
IMAGE_ID="$(docker image inspect jointbuildgs:geogs-official-db40c95-v1 --format '{{.Id}}')"
DEST="$STAGE"
if [ "$STAGE" = depth ]; then DEST=prior; fi
OUT_HOST="$ARTIFACT_HOST/$REGION_REL/$DEST"
OUT_CANON="$ARTIFACT_CANON/$REGION_REL/$DEST"
SCENE_CANON="$ARTIFACT_CANON/$REGION_REL/scene"
LOG_ROOT="$ARTIFACT_HOST/$TASK_REL/input_logs"
test ! -e "$OUT_HOST"
test ! -e "$LOG_ROOT/${REGION}_${STAGE}.command"
mkdir "$OUT_HOST"
DOCKER_ARGS=(docker run --rm --network none --read-only --tmpfs /tmp:rw,size=512m
  --user "$(id -u):$(id -g)" --cpus 4 --memory 12g -w /workspace
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4
  -e MPLCONFIGDIR=/tmp/matplotlib -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  -e "JBGS_CONTAINER_IMAGE_ID=$IMAGE_ID"
  --mount "type=bind,src=$REPO_ROOT,dst=/workspace,readonly"
  --mount "type=bind,src=$ARTIFACT_HOST/$TASK_REL/sources/GeoGS,dst=/geogs,readonly"
  --mount "type=bind,src=$ARTIFACT_HOST/$REGION_REL/surface,dst=$ARTIFACT_CANON/$REGION_REL/surface,readonly"
  --mount "type=bind,src=$OUT_HOST,dst=$OUT_CANON")
for NAME in train_sparse_txt sparse_txt scene_reference_frame.json split_manifest.json; do
  DOCKER_ARGS+=(--mount "type=bind,src=$ARTIFACT_HOST/$REGION_REL/scene/$NAME,dst=$SCENE_CANON/$NAME,readonly")
done
DOCKER_ARGS+=(--entrypoint python "$IMAGE_ID" -m scripts.phd.geogs_p1p2p3_v1.input.prior_native
  --config configs/phd/geogs_p1p2p3_v1/experiment_v1.json --source /geogs
  --scene "$SCENE_CANON" --surface "$ARTIFACT_CANON/$REGION_REL/surface"
  --output "$OUT_CANON" --stage "$STAGE")
(set -o noclobber; printf '%q ' "${DOCKER_ARGS[@]}" > "$LOG_ROOT/${REGION}_${STAGE}.command")
set +e
"${DOCKER_ARGS[@]}" > "$LOG_ROOT/${REGION}_${STAGE}.log" 2>&1
STAGE_EXIT=$?
set -e
(set -o noclobber; printf '%s\n' "$STAGE_EXIT" > "$LOG_ROOT/${REGION}_${STAGE}.exit")
tail -n 8 "$LOG_ROOT/${REGION}_${STAGE}.log"
exit "$STAGE_EXIT"
