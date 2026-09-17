# How to verify this project

Everything here can be checked from a fresh clone. Steps 1 and 2 need no network and take a few seconds.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 by itself) and Node.js 18 or newer for the browser-model test.

```
git clone https://github.com/sachabidermann/airlift-planner
cd airlift-planner
uv sync
```

## One command

```
scripts/check.sh            # all five steps
scripts/check.sh --offline  # steps 1 and 2 only
```

Steps 3 to 5 download about 100 MB into `data/` on the first run, from `earthquake.usgs.gov`, `www2.census.gov` and `davidmegginson.github.io` (OurAirports). GitHub runs the offline steps on every push: see the Actions tab.

## What each step checks

### 1. Unit tests: `uv run pytest -q`

Expected: every test passes (66 at the time of writing). No network; every test builds its own small inputs, except `tests/test_docs.py`, which reads the committed reports.

| file | what it proves |
|---|---|
| `tests/test_usgs.py` | Bilinear lookup is exact on a known plane. A grid listed north to south is flipped correctly. Points outside the grid and empty cells read as not felt. Grids across the 180th meridian work. The legacy `grid.xml` parser handles USGS row order and downsampling. The fallback intensity formula matches all 21 rows of OpenQuake's reference table to 1e-6. PAGER exposure parsing, including PAGER's internal US region codes. An event id cannot escape the cache folder. |
| `tests/test_airbridge.py` | On a small hand-made world: gateway inflow equals the AFPAM formula computed by hand; medium airports are capped at the C-17; shuttle sorties respect fleet hours and ramp limits; capacity never exceeds gateway inflow; a flagged airfield is never used; domestic gateways are preferred; the nearest airfield is the one flagged; the damage center follows people, not open water. |
| `tests/test_small_modules.py` | Usability curve points and interpolation; demand arithmetic; which aircraft fit which runway; water and closed runways are dropped; SFO to LAX is 543 km; Census sampling conserves population. |

### 2. Browser model: `node dashboard/test_model.js`

Expected: `all 135 cases match the Python planner`.

The dashboard runs a JavaScript port of the planner (`docs/model.js`). `dashboard/expected.json` holds the Python planner's answers for 15 events under nine assumption sets that span the dashboard's sliders. For each case the test compares the gateway, metric tons per day, share of need, the airfields flagged, and the forward strips in use.

### 3. Backtests and scenarios: `uv run backtests/run.py`

Writes `backtests/RESULTS.md`. Its first section records the inputs: the download date and SHA-256 of the airport tables, and the ShakeMap version and date for every event. Then a scorecard for the nine real events, a table for the six scenarios, and one section per event with the model's values at the airports that mattered, the plan, what actually happened, and sources.

The tables in `README.md` are copied from this file. `tests/test_docs.py` fails if they disagree.

What happened in each earthquake, and the source for each statement, is in `backtests/events.py`.

### 4. Shaking and population: `uv run backtests/verify_shaking.py`

Writes `backtests/VERIFICATION.md` and exits non-zero if any event's mean difference from PAGER exceeds 0.5.

1. Our grid, read at about 4,150 cities, against the intensity USGS PAGER assigned to each. This tests that the grid is read correctly. It says nothing about whether ShakeMap itself is right.
2. The legacy `grid.xml` parser against the CoverageJSON grid for an event that has both.
3. The fallback distance formula against ShakeMap at every airport in nine events.
4. The Census population reconstruction against real PAGER counts, on US events that have both.

### 5. Dashboard data: `uv run dashboard/build.py`, then step 2 again

Rebuilds `docs/data.json` and `dashboard/expected.json` from fresh downloads and re-runs the browser-model test against them.

## If results differ from the committed files

After step 5, `git status` should show `docs/data.json` changed (it carries a build timestamp and the past week's earthquakes). If `RESULTS.md` also changed, an input changed upstream: OurAirports is updated nightly, and USGS revises ShakeMaps, sometimes years later. Compare the Inputs section of `RESULTS.md` with the committed one to see which.

To re-fetch one event's USGS products: `uv run main.py --quake <id> --refresh`. To start clean, delete `data/`.

## Checking a single claim by hand

```
uv run main.py --quake gllegacyhaywiredm7p05_se     # any USGS event or scenario id
uv run main.py --quake us6000jllz --fleet 24 --forward-km 200
```

The output lists every airfield flagged, the gateway with its inflow, each forward strip with leg, sorties and tons, and the totals. The formulas are in [METHOD.md](METHOD.md), so any line can be recomputed with a calculator. Example, SFO in the HayWired scenario:

    6 spots x 100 t x (20 h / 3.0 h) x 0.85 x 0.929 usability = 3,160 t/day

## The dashboard

```
python3 -m http.server 8766 --directory docs     # then open http://localhost:8766
```

It must be served over HTTP; opening `index.html` as a file will not load the data. The live copy is at https://sachabidermann.github.io/airlift-planner/ and is served from `docs/` on the `main` branch.
