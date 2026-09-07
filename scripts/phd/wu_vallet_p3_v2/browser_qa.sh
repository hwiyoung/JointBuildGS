#!/usr/bin/env bash
set -euo pipefail
wv2_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv2_qa_artifacts=$(realpath "$wv2_qa_repo/../JointBuildGS-artifacts")
wv2_qa_run=${1:-PHD-WU-VALLET-P3-BROWSER-QA-v2}
wv2_qa_url=${2:-http://127.0.0.1:8898/}
wv2_qa_port=${3:-9236}
wv2_qa_output="$wv2_qa_artifacts/phase-payloads/phd/wu_vallet_p3_v2/$wv2_qa_run"
if [[ -e "$wv2_qa_output" ]]; then echo 'New QA output required' >&2; exit 1; fi
if [[ -n $(ss -H -ltn "sport = :$wv2_qa_port") ]]; then
  echo 'Dedicated QA port occupied; existing browser preserved' >&2
  exit 1
fi
command -v google-chrome >/dev/null
command -v node >/dev/null
wv2_qa_profile=$(mktemp -d /tmp/jbgs-wu-p3-v2-qa.XXXXXX)
# Browser QA infrastructure only. No host project scientific dependencies.
google-chrome --headless=new --enable-automation --no-first-run --no-default-browser-check \
  --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$wv2_qa_port" \
  --user-data-dir="$wv2_qa_profile" --disable-dev-shm-usage about:blank \
  >"$wv2_qa_profile/chrome.log" 2>&1 &
wv2_qa_pid=$!
trap 'kill "$wv2_qa_pid" 2>/dev/null || true' EXIT
wv2_qa_ready=0
for wv2_qa_attempt in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$wv2_qa_port/json/version" >/dev/null; then wv2_qa_ready=1; break; fi
  sleep .25
done
if [[ "$wv2_qa_ready" != 1 ]]; then echo "Dedicated browser failed; log: $wv2_qa_profile/chrome.log" >&2; exit 1; fi
node "$wv2_qa_repo/scripts/phd/wu_vallet_p3_v2/browser_qa.mjs" \
  "$wv2_qa_url" "$wv2_qa_output" "$wv2_qa_profile" "$wv2_qa_port"
