#!/usr/bin/env bash
set -euo pipefail
tools="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project="$(dirname "$tools")"
page="$project/results/v0.3/随行-仿真与源码.html"

python3 "$tools/build_viewer.py" "$project" --output "$page"
if command -v firefox >/dev/null 2>&1; then
  firefox --new-window "$page"
else
  xdg-open "$page"
fi
