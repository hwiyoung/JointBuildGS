#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 ))
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
attempt="$(realpath "$1")"
task="$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")"
[[ "$attempt" == "$task/main_v2/photometric_walkthrough_v3_2/"* ]]
[[ -f "$attempt/manifest.json" ]]
image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
exec docker run --rm --read-only --network none --cpus 1 --memory 1g --memory-swap 1g --user "$(id -u):$(id -g)" -w /tmp \
 --mount "type=bind,src=$attempt,dst=/attempt,readonly" \
 --mount "type=bind,src=$task/main_v2/review_site,dst=/site" \
 --mount "type=bind,src=$repo/src/apps/lc_photometry_v3_2,dst=/ui,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/build_photometric_walkthrough_v3_2.py,dst=/build.py,readonly" \
 --entrypoint python "$image" /build.py --attempt /attempt --site /site --ui /ui
