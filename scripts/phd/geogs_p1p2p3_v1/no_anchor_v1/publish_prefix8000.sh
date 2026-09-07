#!/usr/bin/env bash
set -euo pipefail
geogs_pp_profile="${1:?fresh profile identifier}"
[[ "$geogs_pp_profile" =~ ^[A-Za-z0-9_-]+$ ]] || exit 2
geogs_pp_code=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
geogs_pp_repo=$(cd -- "$geogs_pp_code/../../../.." && pwd)
geogs_pp_task=$(realpath "$geogs_pp_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_pp_root="$geogs_pp_task/evaluation/no_anchor_sfm_prefix8000_v1"
geogs_pp_log="$geogs_pp_root/publication/$geogs_pp_profile"
test ! -e "$geogs_pp_log"
test ! -e "$geogs_pp_root/profiles/$geogs_pp_profile"
mkdir -p -- "$geogs_pp_log/code"
cp -- "${BASH_SOURCE[0]}" "$geogs_pp_log/launcher.sh"
cp -- "$geogs_pp_code/prefix8000_v1/build_viewer.py" "$geogs_pp_code/prefix8000_v1/evaluate.py" "$geogs_pp_log/code/"
cp -- "$geogs_pp_code/evaluate.py" "$geogs_pp_log/code/core_evaluate.py"
cp -- "$geogs_pp_code/build_viewer.py" "$geogs_pp_log/code/core_builder.py"
cp -- "$geogs_pp_code/final_retry.py" "$geogs_pp_log/code/"
cp -- "$geogs_pp_task/contracts/sfm_prefix8000_diagnostic_v1.json" "$geogs_pp_log/policy.json"
trap 'geogs_pp_exit=$?; printf "%s\n" "$geogs_pp_exit" > "$geogs_pp_log/exit_code.txt"' EXIT
docker run --rm --network none --read-only --cpus 4 --memory 8g --memory-swap 8g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env NVIDIA_VISIBLE_DEVICES=void \
  --mount "type=bind,src=$geogs_pp_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_pp_root,dst=/out" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python "/out/publication/$geogs_pp_profile/code/build_viewer.py" \
  --task /task --out /out --publish-id "$geogs_pp_profile" \
  --core-evaluator "/out/publication/$geogs_pp_profile/code/core_evaluate.py" \
  --core-builder "/out/publication/$geogs_pp_profile/code/core_builder.py" \
  > "$geogs_pp_log/stdout.log" 2> "$geogs_pp_log/stderr.log"
(cd "$geogs_pp_log" && rg --files -0 -g '!SHA256SUMS' | sort -z | xargs -0 sha256sum) > "$geogs_pp_log/SHA256SUMS"
cat "$geogs_pp_log/stdout.log"
