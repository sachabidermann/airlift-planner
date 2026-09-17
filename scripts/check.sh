#!/bin/sh
# Run every check in the repo.
#
#   scripts/check.sh            all six steps (steps 3-5 download from USGS and the Census Bureau)
#   scripts/check.sh --offline  the tests and the browser-model check only, no network
#
# Steps 3-5 regenerate backtests/RESULTS.md, backtests/VERIFICATION.md,
# docs/data.json and dashboard/expected.json. The airport-table date and hash
# in RESULTS.md differ on any later day. If `git status` shows other
# differences beyond the build timestamp, an input changed upstream:
# OurAirports updates nightly and USGS revises ShakeMaps. RESULTS.md records
# the input hashes and ShakeMap versions so you can tell which.
set -e
cd "$(dirname "$0")/.."

if [ "$1" = "--offline" ]; then
    echo "== unit tests, and README against the committed reports (no network)"
    uv run pytest -q
    echo "== browser model against the Python planner's saved answers (no network)"
    node dashboard/test_model.js
    echo "offline checks passed"
    exit 0
fi

echo "== 1/6 unit tests (no network)"
uv run pytest -q --ignore=tests/test_docs.py

echo "== 2/6 browser model against the Python planner's saved answers (no network)"
node dashboard/test_model.js

echo "== 3/6 backtests and scenarios"
uv run backtests/run.py > /dev/null
echo "wrote backtests/RESULTS.md"

echo "== 4/6 shaking and population verification"
uv run backtests/verify_shaking.py

echo "== 5/6 rebuild dashboard data, then re-check the browser model against it"
uv run dashboard/build.py
node dashboard/test_model.js

echo "== 6/6 README against the regenerated reports"
uv run pytest -q tests/test_docs.py

echo
echo "All checks passed. Files changed by this run:"
git status --short backtests docs dashboard || true
