#!/usr/bin/env bash
set -euo pipefail
wv5_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv5_qa_artifacts=$(realpath "$wv5_qa_repo/../JointBuildGS-artifacts")
wv5_qa_run=${1:-PHD-WU-VALLET-MATCHED-BROWSER-QA-v5}
wv5_qa_url=${2:-http://127.0.0.1:8901/}
wv5_qa_port=${3:-9239}
wv5_qa_output="$wv5_qa_artifacts/phase-payloads/phd/wu_vallet_matched_v5/$wv5_qa_run"
if [[ -e "$wv5_qa_output" ]]; then echo 'New QA output required' >&2; exit 1; fi
if [[ -n $(ss -H -ltn "sport = :$wv5_qa_port") ]]; then
  echo 'Dedicated QA port occupied; existing browser preserved' >&2
  exit 1
fi
command -v google-chrome >/dev/null
command -v node >/dev/null
wv5_qa_profile=$(mktemp -d /tmp/jbgs-wu-matched-v5-qa.XXXXXX)
# Browser QA infrastructure only. No host project scientific dependencies.
google-chrome --headless=new --enable-automation --no-first-run --no-default-browser-check \
  --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$wv5_qa_port" \
  --user-data-dir="$wv5_qa_profile" --disable-dev-shm-usage about:blank \
  >"$wv5_qa_profile/chrome.log" 2>&1 &
wv5_qa_pid=$!
trap 'kill "$wv5_qa_pid" 2>/dev/null || true' EXIT
wv5_qa_ready=0
for wv5_qa_attempt in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$wv5_qa_port/json/version" >/dev/null; then wv5_qa_ready=1; break; fi
  sleep .25
done
if [[ "$wv5_qa_ready" != 1 ]]; then echo "Dedicated browser failed; log: $wv5_qa_profile/chrome.log" >&2; exit 1; fi
node "$wv5_qa_repo/scripts/phd/wu_vallet_matched_v5/browser_qa.mjs" \
  "$wv5_qa_url" "$wv5_qa_output" "$wv5_qa_profile" "$wv5_qa_port"
