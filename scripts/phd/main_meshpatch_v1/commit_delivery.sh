#!/usr/bin/env bash
# Explicit paths only; --only prevents unrelated staged work entering this commit.
set -euo pipefail
REPO=${JBGS_MESHPATCH_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}
cd "$REPO"
[[ $(git branch --show-current) == exp/main-experiment ]]
event=${1:?patch or mesh}
paths=(configs/phd/main_meshpatch_v1 scripts/phd/main_meshpatch_v1 docs/experiments/phd/main_meshpatch_v1)
git add -- "${paths[@]}"
git diff --cached --check -- "${paths[@]}"
if ! git diff --cached --quiet -- "${paths[@]}"; then
  git commit --only -m "[PHD-MAIN-MESHPATCH-v1] deliver $event measurements and validation" -- "${paths[@]}"
fi
git push origin HEAD:exp/main-experiment
git rev-parse HEAD
