#!/usr/bin/env bash
set -euo pipefail
(( $# == 2 ))
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task="$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")"
attempt="$(realpath "$1")"
evaluation="$(realpath "$2")"
[[ "$attempt" == "$task/main_v2/normal_photometry_v3_7/attempt_"* ]]
[[ "$evaluation" == "$task/main_v2/normal_photometry_v3_7/evaluation_"*/payload ]]
exec docker run --rm --read-only --network none --cpus 1 --memory 1g --memory-swap 1g --user "$(id -u):$(id -g)" \
 --mount "type=bind,src=$attempt,dst=/attempt,readonly" \
 --mount "type=bind,src=$evaluation,dst=/evaluation,readonly" \
 --mount "type=bind,src=$task/main_v2/review_site,dst=/site" \
 --mount "type=bind,src=$repo/src/apps/lc_normal_photometry_v3_7,dst=/ui,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/build_normal_photometry_v3_7.py,dst=/build.py,readonly" \
 --entrypoint python sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
 /build.py --attempt /attempt --evaluation /evaluation --site /site --ui /ui
