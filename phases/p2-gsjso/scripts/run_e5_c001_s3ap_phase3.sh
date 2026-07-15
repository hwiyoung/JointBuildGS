#!/usr/bin/env bash
# S3-A-prime Phase 3.  The Python entrypoint is orchestration only; every
# render/read-out/score worker it starts is a pinned Docker container with
# --user uid:gid.  No host scientific package is imported by the controller.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"
exec python3 phases/p2-gsjso/scripts/e5_c001_s3ap_phase3.py run "$@"
