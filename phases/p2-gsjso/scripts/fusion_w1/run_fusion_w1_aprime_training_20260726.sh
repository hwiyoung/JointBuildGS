#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
driver="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_training_20260726.py"
test_driver="tests/fusion_w1/test_fusion_w1_aprime_training_20260726.py"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 {test|materialize|check|launch|queue-plan|queue-next} [arguments...]" >&2
  exit 2
fi

command_name="$1"
shift
cd "$repo_root"

case "$command_name" in
  test)
    docker compose run --rm --no-deps -T dev python "$test_driver" "$@"
    ;;
  materialize|check|queue-plan|queue-next)
    # Bind-mounted run artifacts must remain writable by the host-side launcher.
    # The Compose service otherwise defaults to root and leaves materialized job
    # directories unable to accept started/completed/failed receipts.
    docker compose run --rm --no-deps -T \
      --user "$(id -u):$(id -g)" \
      dev python "$driver" "$command_name" "$@"
    ;;
  launch)
    python3 "$driver" launch "$@"
    ;;
  *)
    echo "unknown command: $command_name" >&2
    exit 2
    ;;
esac
