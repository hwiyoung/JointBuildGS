#!/usr/bin/env bash
set -euo pipefail
p3_qa_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
p3_qa_artifacts=$(realpath "$p3_qa_repo/../JointBuildGS-artifacts")
p3_qa_run=${1:-PHD-WU-VALLET-P3-BROWSER-QA-v1}
p3_qa_url=${2:-http://127.0.0.1:8897/}
p3_qa_port=${3:-9235}
p3_qa_output="$p3_qa_artifacts/phase-payloads/phd/wu_vallet_p3_v1/$p3_qa_run"
if [[ -e "$p3_qa_output" ]]; then echo "New QA output required" >&2; exit 1; fi
if ss -ltn "sport = :$p3_qa_port" | tail -n +2 | read -r _; then
  echo "Dedicated browser QA port is occupied; existing browser left untouched" >&2
  exit 1
fi
command -v google-chrome >/dev/null
command -v node >/dev/null
p3_qa_profile=$(mktemp -d /tmp/jbgs-wu-p3-qa.XXXXXX)
# jointbuildgs:dev has no node/chrome (read-only command-v inspection). This
# wrapper is host browser-QA infrastructure using Node built-ins, no project
# dependencies. Processing, training, evaluation and viewer build remain Docker.
google-chrome --headless=new --enable-automation --no-first-run --no-default-browser-check \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$p3_qa_port" \
  --user-data-dir="$p3_qa_profile" --disable-dev-shm-usage about:blank \
  >"$p3_qa_profile/chrome.log" 2>&1 &
p3_qa_pid=$!
trap 'kill "$p3_qa_pid" 2>/dev/null || true' EXIT
p3_qa_ready=0
for p3_qa_attempt in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$p3_qa_port/json/version" >/dev/null; then p3_qa_ready=1; break; fi
  sleep .25
done
if [[ "$p3_qa_ready" != 1 ]]; then echo "Dedicated browser did not start; log: $p3_qa_profile/chrome.log" >&2; exit 1; fi
node "$p3_qa_repo/scripts/phd/wu_vallet_p3_v1/browser_qa.mjs" \
  "$p3_qa_url" "$p3_qa_output" "$p3_qa_profile" "$p3_qa_port"
