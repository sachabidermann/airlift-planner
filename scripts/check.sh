#!/bin/sh
# Run every check in the repo.
#
#   scripts/check.sh            all five steps (steps 3-5 download from USGS and the Census Bureau)
#   scripts/check.sh --offline  steps 1 and 2 only, no network
#
# Steps 3-5 regenerate backtests/RESULTS.md, backtests/VERIFICATION.md,
# docs/data.json and dashboard/expected.json. If `git status` then shows
# differences beyond the build timestamp, an input changed upstream:
# OurAirports updates nightly and USGS revises ShakeMaps. RESULTS.md records
# the input hashes and ShakeMap versions so you can tell which.
set -e
cd "$(dirname "$0")/.."

echo "== 1/5 unit tests (no network)"
uv run pytest -q

echo "== 2/5 browser model against the Python planner's saved answers (no network)"
node dashboard/test_model.js

if [ "$1" = "--offline" ]; then
    echo "offline checks passed"
    exit 0
fi

echo "== 3/5 backtests and scenarios"
uv run backtests/run.py > /dev/null
echo "wrote backtests/RESULTS.md"

echo "== 4/5 shaking and population verification"
uv run backtests/verify_shaking.py

echo "== 5/5 rebuild dashboard data, then re-check the browser model against it"
uv run dashboard/build.py
node dashboard/test_model.js

echo
echo "All checks passed. Files changed by this run:"
git status --short backtests docs dashboard || true
