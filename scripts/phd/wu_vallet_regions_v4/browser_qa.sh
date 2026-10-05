#!/usr/bin/env bash
set -euo pipefail
wv4_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv4_qa_artifacts=$(realpath "$wv4_qa_repo/../JointBuildGS-artifacts")
wv4_qa_run=${1:-PHD-WU-VALLET-REGIONS-BROWSER-QA-v4}
wv4_qa_url=${2:-http://127.0.0.1:8900/}
wv4_qa_port=${3:-9238}
wv4_qa_output="$wv4_qa_artifacts/phase-payloads/phd/wu_vallet_regions_v4/$wv4_qa_run"
if [[ -e "$wv4_qa_output" ]]; then echo 'New QA output required' >&2; exit 1; fi
if [[ -n $(ss -H -ltn "sport = :$wv4_qa_port") ]]; then
  echo 'Dedicated QA port occupied; existing browser preserved' >&2
  exit 1
fi
command -v google-chrome >/dev/null
command -v node >/dev/null
wv4_qa_profile=$(mktemp -d /tmp/jbgs-wu-p3-regions-v4-qa.XXXXXX)
# Browser QA infrastructure only. No host project scientific dependencies.
google-chrome --headless=new --enable-automation --no-first-run --no-default-browser-check \
  --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$wv4_qa_port" \
  --user-data-dir="$wv4_qa_profile" --disable-dev-shm-usage about:blank \
  >"$wv4_qa_profile/chrome.log" 2>&1 &
wv4_qa_pid=$!
trap 'kill "$wv4_qa_pid" 2>/dev/null || true' EXIT
wv4_qa_ready=0
for wv4_qa_attempt in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$wv4_qa_port/json/version" >/dev/null; then wv4_qa_ready=1; break; fi
  sleep .25
done
if [[ "$wv4_qa_ready" != 1 ]]; then echo "Dedicated browser failed; log: $wv4_qa_profile/chrome.log" >&2; exit 1; fi
node "$wv4_qa_repo/scripts/phd/wu_vallet_regions_v4/browser_qa.mjs" \
  "$wv4_qa_url" "$wv4_qa_output" "$wv4_qa_profile" "$wv4_qa_port"
