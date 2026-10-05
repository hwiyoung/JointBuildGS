#!/usr/bin/env bash
set -euo pipefail
(( $# == 0 ))
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
main=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1/main_v2")
launch=$(mktemp -d "$main/contribution_review_v2_2/report_launch_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
cp "$repo/scripts/phd/local_complementary_refinement_v1/build_contribution_report_v2_2.py" "${BASH_SOURCE[0]}" "$launch/"
cp "$repo/docs/experiments/phd/local_complementary_refinement_v1/CONTRIBUTION_ASSESSMENT_ko_v2_2.md" "$launch/"
git -C "$repo" rev-parse HEAD > "$launch/git_commit.txt"
command=(docker run --rm --read-only --network none --cpus 2 --memory 3g --memory-swap 3g -w /tmp \
 --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 -e MPLCONFIGDIR=/tmp/mpl \
 --tmpfs /tmp:rw,nosuid,size=128m \
 --mount "type=bind,src=$launch,dst=/report,readonly" \
 --mount "type=bind,src=$main/contribution_review_v2_2,dst=/analysis,readonly" \
 --mount "type=bind,src=$main/review_site,dst=/site" \
 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
 python /report/build_contribution_report_v2_2.py \
 --analysis /analysis/attempt_20260911T025441_538040Z \
 --qa /analysis/independent_qa_20260911T025738_YIKw5s/receipt.json \
 --report /report/CONTRIBUTION_ASSESSMENT_ko_v2_2.md --site /site)
printf '%q ' "${command[@]}" > "$launch/command.sh"
printf '\n' >> "$launch/command.sh"
set +e
"${command[@]}" > "$launch/stdout.log" 2> "$launch/stderr.log"
code=$?
set -e
printf '%s\n' "$code" > "$launch/exit_code.txt"
cat "$launch/stdout.log"
if (( code )); then cat "$launch/stderr.log" >&2; fi
exit "$code"
