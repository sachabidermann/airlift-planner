// Checks the browser model reproduces the Python planner for the default assumptions.
//   node dashboard/test_model.js
const fs = require("fs");
const path = require("path");
const M = require(path.join(__dirname, "..", "docs", "model.js"));
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "docs", "data.json"), "utf8"));

// Expected values are copied from `uv run backtests/run.py` output.
const expected = {
  usp000h60h: { gateway: "MTPP", delivered: 3276 },
  us20002926: { gateway: "VNKT", delivered: 4212 },
  us6000jllz: { gateway: "LTAU", delivered: 784 },
  us7000kufc: { gateway: "GMMX", delivered: 5008 },
  us7000pn9s: { gateway: "VYHH", delivered: 1905 },
};

let failures = 0;
for (const ev of data.events) {
  const plan = M.build(ev, data, data.defaults);
  const gw = plan.chosen ? plan.chosen.gateway.field.ident : null;
  const d = Math.round(plan.delivered);
  const exp = expected[ev.id];
  let status = "";
  if (exp) {
    const ok = exp.gateway === gw && Math.abs(exp.delivered - d) <= 1;
    status = ok ? "OK" : `MISMATCH (expected ${exp.gateway} ${exp.delivered})`;
    if (!ok) failures++;
  }
  console.log(`${ev.id.padEnd(12)} ${String(gw).padEnd(8)} ${String(d).padStart(6)} t/day  ${status}`);
}
console.log(failures ? `${failures} mismatch(es)` : "all backtests match the Python planner");
process.exit(failures ? 1 : 0);
