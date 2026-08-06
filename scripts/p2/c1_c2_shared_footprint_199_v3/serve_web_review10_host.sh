#!/usr/bin/env bash
set -euo pipefail

echo "NOTICE: legacy wrapper now serves the active exact frozen-row package." >&2
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/serve_web_review199_exact_rows_host.sh" "$@"
