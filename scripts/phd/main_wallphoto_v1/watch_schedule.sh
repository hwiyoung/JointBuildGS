#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1"
docker run -d --restart on-failure:3 --read-only --network none --name jbgs-wallphoto-schedule \
 --user "$(id -u):$(id -g)" --cpus 1 --memory 2g --memory-swap 2g \
 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e TZ=Asia/Seoul \
 -v "$REPO/scripts/phd/main_wallphoto_v1:/scripts:ro" \
 -v "$REPO/configs/phd/main_wallphoto_v1:/cfg:ro" \
 -v "$REPO/docs/experiments/phd/main_wallphoto_v1:/docs:rw" -v "$OUT:/out:rw" \
 --entrypoint nice jointbuildgs:dev -n 19 python -B -u /scripts/package.py --watch
