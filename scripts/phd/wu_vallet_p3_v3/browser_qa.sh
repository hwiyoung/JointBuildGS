#!/usr/bin/env bash
set -euo pipefail
wv3_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv3_qa_artifacts=$(realpath "$wv3_qa_repo/../JointBuildGS-artifacts")
wv3_qa_run=${1:-PHD-WU-VALLET-P3-BROWSER-QA-v3}
wv3_qa_url=${2:-http://127.0.0.1:8899/}
wv3_qa_port=${3:-9237}
wv3_qa_output="$wv3_qa_artifacts/phase-payloads/phd/wu_vallet_p3_v3/$wv3_qa_run"
if [[ -e "$wv3_qa_output" ]]; then echo 'New QA output required' >&2; exit 1; fi
if [[ -n $(ss -H -ltn "sport = :$wv3_qa_port") ]]; then
  echo 'Dedicated QA port occupied; existing browser preserved' >&2
  exit 1
fi
command -v google-chrome >/dev/null
command -v node >/dev/null
wv3_qa_profile=$(mktemp -d /tmp/jbgs-wu-p3-v3-qa.XXXXXX)
# Browser QA infrastructure only. No host project scientific dependencies.
google-chrome --headless=new --enable-automation --no-first-run --no-default-browser-check \
  --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$wv3_qa_port" \
  --user-data-dir="$wv3_qa_profile" --disable-dev-shm-usage about:blank \
  >"$wv3_qa_profile/chrome.log" 2>&1 &
wv3_qa_pid=$!
trap 'kill "$wv3_qa_pid" 2>/dev/null || true' EXIT
wv3_qa_ready=0
for wv3_qa_attempt in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$wv3_qa_port/json/version" >/dev/null; then wv3_qa_ready=1; break; fi
  sleep .25
done
if [[ "$wv3_qa_ready" != 1 ]]; then echo "Dedicated browser failed; log: $wv3_qa_profile/chrome.log" >&2; exit 1; fi
node "$wv3_qa_repo/scripts/phd/wu_vallet_p3_v3/browser_qa.mjs" \
  "$wv3_qa_url" "$wv3_qa_output" "$wv3_qa_profile" "$wv3_qa_port"
