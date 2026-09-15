// Checks the browser model reproduces the Python planner for the default assumptions.
//   node dashboard/test_model.js
const fs = require("fs");
const path = require("path");
const M = require(path.join(__dirname, "..", "docs", "model.js"));
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "docs", "data.json"), "utf8"));

// Expected values are copied from `uv run backtests/run.py` output.
const expected = {
  nc216859: { gateway: "KSFO", delivered: 4898 },
  ak20419010: { gateway: "PANC", delivered: 4680 },
  ci38457511: { gateway: "KMHV", delivered: 2053 },
  us70006vll: { gateway: "TJSJ", delivered: 4342 },
  usp000h60h: { gateway: "MTPP", delivered: 3276 },
  us20002926: { gateway: "VNKT", delivered: 4212 },
  us6000jllz: { gateway: "LTAJ", delivered: 4716 },
  us7000kufc: { gateway: "GMMX", delivered: 5008 },
  us7000pn9s: { gateway: "VYHH", delivered: 1905 },
  gllegacyhaywiredm7p05_se: { gateway: "KSFO", delivered: 4866 },
  sclegacyshakeout2full_se: { gateway: "KLGB", delivered: 5008 },
  gllegacycasc9p0expanded_se: { gateway: "KTCM", delivered: 1554 },
  wa22sfz01_se: { gateway: "KNUW", delivered: 2029 },
  nm19fema_m7p7_mt_se: { gateway: "KMEM", delivered: 4716 },
  caribe25puertorico_2_se: { gateway: "TJSJ", delivered: 3276 },
};

let failures = 0, checked = 0;
for (const ev of data.events) {
  const plan = M.build(ev, data, data.defaults);
  const gw = plan.chosen ? plan.chosen.gateway.field.ident : null;
  const d = Math.round(plan.delivered);
  const exp = expected[ev.id];
  let status = "";
  if (exp) {
    checked++;
    const ok = exp.gateway === gw && Math.abs(exp.delivered - d) <= 1;
    status = ok ? "OK" : `MISMATCH (expected ${exp.gateway} ${exp.delivered})`;
    if (!ok) failures++;
  }
  console.log(`${ev.id.padEnd(28)} ${String(gw).padEnd(8)} ${String(d).padStart(6)} t/day  ${status}`);
}
console.log(failures ? `${failures} mismatch(es) in ${checked} checked` : `all ${checked} backtests and scenarios match the Python planner`);
process.exit(failures ? 1 : 0);
