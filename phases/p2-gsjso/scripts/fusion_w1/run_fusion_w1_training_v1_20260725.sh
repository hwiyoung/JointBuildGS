#!/usr/bin/env bash
# Fusion W1 §4: immutable config materialization and one foreground Docker job.
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_training_v1_20260725.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_training_v1_20260725.py"
TEST="tests/fusion_w1/test_fusion_w1_training_v1_20260725.py"
IMAGE="jointbuildgs:dev"
IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"

assert_image() {
  local observed
  observed="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
  if [[ "$observed" != "$IMAGE_ID" ]]; then
    echo "training image ID mismatch: observed=$observed expected=$IMAGE_ID" >&2
    exit 2
  fi
}

run_python_in_image() {
  docker run --rm \
    --pull=never \
    --network=none \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$IMAGE" "$@"
}

case "${1:-}" in
  test)
    assert_image
    run_python_in_image -m unittest -v "$TEST"
    ;;
  materialize)
    [[ $# -eq 4 ]] || {
      echo "usage: $0 materialize DEBY_LOD2_<id> {A|B} {r1|r2}" >&2
      exit 2
    }
    assert_image
    run_python_in_image "$SCRIPT" --config "$CONFIG" materialize \
      --building-id "$2" --arm "$3" --run "$4"
    ;;
  check)
    [[ $# -eq 4 ]] || {
      echo "usage: $0 check DEBY_LOD2_<id> {A|B} {r1|r2}" >&2
      exit 2
    }
    assert_image
    run_python_in_image "$SCRIPT" --config "$CONFIG" check \
      --building-id "$2" --arm "$3" --run "$4"
    ;;
  aggregate-loss-shares)
    [[ $# -eq 4 ]] || {
      echo "usage: $0 aggregate-loss-shares DEBY_LOD2_<id> {A|B} {r1|r2}" >&2
      exit 2
    }
    assert_image
    run_python_in_image "$SCRIPT" --config "$CONFIG" aggregate-loss-shares \
      --building-id "$2" --arm "$3" --run "$4"
    ;;
  launch)
    [[ $# -eq 5 ]] || {
      echo "usage: $0 launch DEBY_LOD2_<id> {A|B} {r1|r2} {0|1}" >&2
      exit 2
    }
    [[ "$5" == "0" || "$5" == "1" ]] || {
      echo "physical GPU must be 0 or 1" >&2
      exit 2
    }
    assert_image
    # Host Python is orchestration only. The script launches all numerical
    # processing through the pinned Docker Compose service.
    exec python3 "$SCRIPT" --config "$CONFIG" launch \
      --building-id "$2" --arm "$3" --run "$4" --gpu "$5"
    ;;
  retry-infra)
    [[ $# -eq 5 ]] || {
      echo "usage: $0 retry-infra DEBY_LOD2_<id> {A|B} {r1|r2} {0|1}" >&2
      exit 2
    }
    [[ "$5" == "0" || "$5" == "1" ]] || {
      echo "physical GPU must be 0 or 1" >&2
      exit 2
    }
    assert_image
    # The retry command preserves the original receipts and runs the one
    # approved pre-optimizer infrastructure attempt in a separate namespace.
    exec python3 "$SCRIPT" --config "$CONFIG" retry-infra \
      --building-id "$2" --arm "$3" --run "$4" --gpu "$5"
    ;;
  *)
    echo "usage: $0 {test|materialize|check|aggregate-loss-shares|launch|retry-infra} ..." >&2
    exit 2
    ;;
esac
