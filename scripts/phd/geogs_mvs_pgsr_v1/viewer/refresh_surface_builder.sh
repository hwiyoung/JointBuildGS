#!/usr/bin/env bash
# CPU-only staged update; preserve the existing builder as a stopped rollback container.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
artifact="$(realpath "$repo/../JointBuildGS-artifacts")"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
task="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
reference="$artifact/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run"
raw="$artifact/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz"
output="$task/viewer_rgb_v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
name=jbgs-geogs-rgb-builder-v1
test "$(docker inspect --format '{{.State.Running}}' "$name")" = true
test "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/out"}}{{.Source}}{{end}}{{end}}' "$name")" = "$output"
mkdir -p "$output/surface_only_updates"
update="$(mktemp -d "$output/surface_only_updates/attempt.XXXXXXXX")"
source_snapshot="$(mktemp -d "$output/sources/attempt.XXXXXXXX")"
mkdir "$update/stage"
cp -p "$repo/scripts/phd/geogs_mvs_pgsr_v1/viewer/"*.py "$source_snapshot/"
cp -p "$repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$source_snapshot/mvs_depth.py"
cp -p "$repo/configs/phd/geogs_mvs_pgsr_v1/viewer_rgb_v1.json" "$source_snapshot/config.json"
cp -p "${BASH_SOURCE[0]}" "$source_snapshot/refresh_surface_builder.sh"
git -C "$repo" rev-parse HEAD > "$source_snapshot/operator_head.txt"
sha256sum "$source_snapshot/"*.py "$source_snapshot/config.json" "$source_snapshot/refresh_surface_builder.sh" > "$source_snapshot/sha256sums.txt"
printf '%s\n' "$source_snapshot" > "$update/source_snapshot.txt"
docker inspect "$name" > "$update/previous_builder.json"
common=(--read-only --cap-drop ALL --security-opt no-new-privileges --user "$(id -u):$(id -g)"
  --network none --cpus 2 --memory 12g --shm-size 256m --tmpfs /tmp:rw,nosuid,size=256m
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  --env MKL_NUM_THREADS=2 --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --mount "type=bind,src=$source_snapshot,dst=/driver,readonly"
  --mount "type=bind,src=$source_snapshot/config.json,dst=/config.json,readonly"
  --mount "type=bind,src=$base,dst=/base,readonly"
  --mount "type=bind,src=$task,dst=/new,readonly"
  --mount "type=bind,src=$reference,dst=/reference,readonly"
  --mount "type=bind,src=$raw,dst=/raw/uas.laz,readonly")
build=(python /driver/build.py --base /base --new /new --reference /reference
  --raw-uas /raw/uas.laz --output /out --config /config.json)
printf '%s\n' "$update"
docker run --rm "${common[@]}" --mount "type=bind,src=$update/stage,dst=/out" \
  "$image" "${build[@]}" > "$update/stage.log" 2>&1
publish=(docker run --rm "${common[@]}" --mount "type=bind,src=$output,dst=/live"
  "$image" python /driver/publish_surface_update.py --stage "/live/surface_only_updates/$(basename "$update")/stage" --live /live)
"${publish[@]}" > "$update/validation.json"
rollback="$name-rollback-$(basename "$update" | tr '[:upper:]' '[:lower:]')"
printf '%s\n' "$rollback" > "$update/rollback_container.txt"
# On failure, preserve the failed replacement and restore the original builder.
recover() {
  result=$?
  if [[ "$result" -ne 0 ]]; then
    set +e
    if docker container inspect "$rollback" >/dev/null 2>&1; then
      if docker container inspect "$name" >/dev/null 2>&1; then
        docker stop --time 10 "$name" >/dev/null 2>&1
        docker rename "$name" "$name-failed-$(basename "$update" | tr '[:upper:]' '[:lower:]')"
      fi
      docker rename "$rollback" "$name"
    fi
    "${publish[@]}" --restore
    docker start "$name"
    printf 'FAIL_RECOVERY_ATTEMPTED_CHECK_CONTAINER_AND_METADATA\n' > "$update/status.txt"
  fi
}
trap recover EXIT
docker stop --time 30 "$name" > "$update/stop.txt"
docker rename "$name" "$rollback"
"${publish[@]}" --publish > "$update/publication.log"
docker run -d --name "$name" --restart unless-stopped "${common[@]}" \
  --mount "type=bind,src=$output,dst=/out" "$image" "${build[@]}" --watch > "$update/new_builder_id.txt"
test "$(docker inspect --format '{{.State.Running}}' "$name")" = true
docker inspect "$name" > "$update/new_builder.json"
printf 'PASS_PUBLISHED_BUILDER_STARTED\n' > "$update/status.txt"
trap - EXIT
cat "$update/publication_receipt.json"
printf '%s\n' "$update"
