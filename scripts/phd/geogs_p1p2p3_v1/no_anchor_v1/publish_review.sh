#!/usr/bin/env bash
set -euo pipefail
geogs_pr_profile="${1:?unique profile id}"
geogs_pr_mode=complete
shift
if [[ ${1:-} == complete || ${1:-} == partial ]]; then
  geogs_pr_mode="$1"
  shift
fi
geogs_pr_overrides=()
while (( $# )); do
  case "$1" in
    --region-experiment) test "$#" -ge 2; geogs_pr_overrides+=("$1" "$2"); shift 2 ;;
    *) printf 'Unknown publication argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
case "$geogs_pr_profile" in *[!a-zA-Z0-9_-]*|'') exit 2 ;; esac
case "$geogs_pr_mode" in complete|partial) ;; *) exit 2 ;; esac
geogs_pr_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_pr_task=$(realpath "$geogs_pr_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_pr_out="$geogs_pr_task/evaluation/no_anchor_sfm_v1"
geogs_pr_log="$geogs_pr_out/publication/$geogs_pr_profile"
test ! -e "$geogs_pr_log"
mkdir -p -- "$geogs_pr_log/code"
cp -- "${BASH_SOURCE[0]}" "$geogs_pr_log/launcher_snapshot.sh"
cp -- "$geogs_pr_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/"{build_viewer.py,summarize_resources.py,compare_reference_support.py,figures.py,final_retry.py} "$geogs_pr_log/code/"
trap 'geogs_pr_exit=$?; printf "%s\n" "$geogs_pr_exit" > "$geogs_pr_log/exit_code.txt"' EXIT
geogs_pr_common=(--rm --network none --cpus 4 --memory 16g --memory-swap 16g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --env OMP_NUM_THREADS=4 --env OPENBLAS_NUM_THREADS=4 --env MPLCONFIGDIR=/tmp/geogs-matplotlib
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --mount "type=bind,src=$geogs_pr_task,dst=/task,readonly"
  --mount "type=bind,src=$geogs_pr_out,dst=/out"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e)
# The selector reads the frozen finite policy and sealed amendments only. Its
# exact regional choices remain fixed throughout this publication, even if an
# additional eligible preparation appears while figures/resources are built.
geogs_pr_selection_command=(docker run "${geogs_pr_common[@]}" python "/out/publication/$geogs_pr_profile/code/final_retry.py"
  --task /task --out "/out/publication/$geogs_pr_profile/selection.json" "${geogs_pr_overrides[@]}")
printf '%q ' "${geogs_pr_selection_command[@]}" > "$geogs_pr_log/selection_command.sh"
printf '\n' >> "$geogs_pr_log/selection_command.sh"
"${geogs_pr_selection_command[@]}" > "$geogs_pr_log/selection_stdout.log" 2> "$geogs_pr_log/selection_stderr.log"
mapfile -t geogs_pr_regions < "$geogs_pr_log/selection.args"
docker run "${geogs_pr_common[@]}" python "/out/publication/$geogs_pr_profile/code/build_viewer.py" \
  --task /task --out /out --publish-id "$geogs_pr_profile" \
  --selection-record "evaluation/no_anchor_sfm_v1/publication/$geogs_pr_profile/selection.json" \
  --source-manifest-sha256 12ba0d9a54b7313a7ded96fb9ceb255d0489948e1e18f4d3dadfb1ebcfda61d6 \
  "${geogs_pr_regions[@]}" > "$geogs_pr_log/viewer_stdout.log" 2> "$geogs_pr_log/viewer_stderr.log"
docker run "${geogs_pr_common[@]}" python "/out/publication/$geogs_pr_profile/code/summarize_resources.py" \
  --task /task --experiment /task/no_anchor_sfm_v1 --out "/out/resources_$geogs_pr_profile" \
  "${geogs_pr_regions[@]}" > "$geogs_pr_log/resources_stdout.log" 2> "$geogs_pr_log/resources_stderr.log"
geogs_pr_partial=()
if [[ "$geogs_pr_mode" == partial ]]; then
  geogs_pr_partial=(--allow-partial --availability-manifest "/out/profiles/$geogs_pr_profile/availability.json")
fi
docker run "${geogs_pr_common[@]}" python "/out/publication/$geogs_pr_profile/code/compare_reference_support.py" \
  --task /task --out /out --output-relative "support_$geogs_pr_profile" "${geogs_pr_partial[@]}" \
  > "$geogs_pr_log/support_stdout.log" 2> "$geogs_pr_log/support_stderr.log"
if [[ "$geogs_pr_mode" == complete ]]; then
  docker run "${geogs_pr_common[@]}" python "/out/publication/$geogs_pr_profile/code/figures.py" \
    --task /task --out /out --support-relative "support_$geogs_pr_profile" --output-relative "figures_$geogs_pr_profile" \
    > "$geogs_pr_log/figures_stdout.log" 2> "$geogs_pr_log/figures_stderr.log"
fi
cat "$geogs_pr_log/viewer_stdout.log"
