// Checks that docs/model.js (the browser port) reproduces the Python planner.
//
//   node dashboard/test_model.js
//
// dashboard/expected.json is written by `uv run dashboard/build.py` from
// airlift.airbridge.build_plan, for every backtest and scenario under nine
// assumption sets that span the dashboard's sliders. For each case this test
// compares the gateway, tonnes delivered, share of need, the airfields flagged
// as knocked out and the forward strips in use.
const fs = require("fs");
const path = require("path");
const M = require(path.join(__dirname, "..", "docs", "model.js"));
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "docs", "data.json"), "utf8"));
const expected = JSON.parse(fs.readFileSync(path.join(__dirname, "expected.json"), "utf8"));

const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
let checked = 0;
const failures = [];

for (const [id, cases] of Object.entries(expected.events)) {
  const ev = data.events.find((e) => e.id === id);
  if (!ev) { failures.push(`${id}: missing from docs/data.json`); continue; }
  for (const c of cases) {
    const plan = M.build(ev, data, { ...data.defaults, ...c.assumptions });
    const got = {
      gateway: plan.chosen ? plan.chosen.gateway.field.ident : null,
      delivered: plan.delivered,
      coverage: plan.coverage,
      traps: plan.traps.map((t) => t.ident).sort(),
      forwards: (plan.chosen ? plan.chosen.forwards : []).filter((f) => f.sorties >= 0.5).map((f) => f.field.ident).sort(),
    };
    const problems = [];
    if (got.gateway !== c.gateway) problems.push(`gateway ${got.gateway} != ${c.gateway}`);
    if (Math.abs(got.delivered - c.delivered) > 0.5) problems.push(`delivered ${got.delivered.toFixed(1)} != ${c.delivered}`);
    if ((got.coverage === null) !== (c.coverage === null) || (c.coverage !== null && Math.abs(got.coverage - c.coverage) > 1e-3 * Math.max(1, c.coverage))) problems.push(`coverage ${got.coverage} != ${c.coverage}`);
    if (!same(got.traps, c.traps)) problems.push(`traps [${got.traps}] != [${c.traps}]`);
    if (!same(got.forwards, c.forwards)) problems.push(`forwards [${got.forwards}] != [${c.forwards}]`);
    checked++;
    if (problems.length) failures.push(`${id} ${JSON.stringify(c.assumptions)}: ${problems.join("; ")}`);
  }
}

for (const f of failures) console.log("MISMATCH", f);
console.log(failures.length ? `${failures.length} of ${checked} cases differ from the Python planner` : `all ${checked} cases match the Python planner`);
process.exit(failures.length ? 1 : 0);
