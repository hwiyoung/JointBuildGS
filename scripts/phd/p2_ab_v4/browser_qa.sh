#!/usr/bin/env bash
set -euo pipefail
v4_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
v4_artifacts=$(realpath "$v4_repo/../JointBuildGS-artifacts")
v4_browser_profile=$(mktemp -d /tmp/jbgs-p2-ab-v4-qa.XXXXXX)
v4_browser_output="$v4_artifacts/phase-payloads/phd/p2_ab_v4/PHD-P2-AB-V4-BROWSER-QA-v1"
v4_browser_port=9230
if ss -ltn "sport = :$v4_browser_port" | tail -n +2 | read -r _; then
  echo "Dedicated browser QA port is already occupied" >&2
  exit 1
fi
google-chrome --headless=new --enable-automation --no-first-run --no-default-browser-check \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$v4_browser_port" \
  --user-data-dir="$v4_browser_profile" --disable-dev-shm-usage about:blank \
  >"$v4_browser_profile/chrome.log" 2>&1 &
v4_browser_pid=$!
trap 'kill "$v4_browser_pid" 2>/dev/null || true' EXIT
for v4_attempt in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:$v4_browser_port/json/version" >/dev/null; then break; fi
  sleep .25
done
node "$v4_repo/scripts/phd/p2_ab_v4/browser_qa.mjs" \
  'http://127.0.0.1:8895/PHD-P2-AB-V4-QUALITATIVE-v1/viewer/?view=333' \
  "$v4_browser_output" "$v4_browser_profile" "$v4_browser_port"
