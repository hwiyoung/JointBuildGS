#!/usr/bin/env bash
set -euo pipefail

echo "NOTICE: browser JPEG/SVG projection is superseded; delegating to the exact frozen-row builder." >&2
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_web_review199_exact_rows_host.sh" "$@"
