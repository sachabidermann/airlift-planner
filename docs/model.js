/* Airlift Planner airbridge model: browser port of airlift/airbridge.py,
   demand.py and survivability.py. Pure functions, no DOM.

   `node dashboard/test_model.js` checks this file against the Python planner
   for every backtest and scenario under nine assumption sets. Change the
   Python first, rebuild with `uv run dashboard/build.py`, then make this match. */
(function (root) {
  "use strict";

  const R_EARTH = 6371.0;

  function haversine(lat1, lon1, lat2, lon2) {
    const p1 = (lat1 * Math.PI) / 180, p2 = (lat2 * Math.PI) / 180;
    const dp = p2 - p1, dl = ((lon2 - lon1) * Math.PI) / 180;
    const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * R_EARTH * Math.asin(Math.sqrt(a));
  }

  // survivability.runway_usability
  function usability(curve, mmi) {
    if (mmi <= curve[0][0]) return curve[0][1];
    if (mmi >= curve[curve.length - 1][0]) return curve[curve.length - 1][1];
    for (let i = 0; i < curve.length - 1; i++) {
      const [m0, p0] = curve[i], [m1, p1] = curve[i + 1];
      if (m0 <= mmi && mmi <= m1) return p0 + ((p1 - p0) * (mmi - m0)) / (m1 - m0);
    }
    return curve[curve.length - 1][1];
  }

  // survivability.roman: halves round up
  function roman(mmi) {
    const n = ["-", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
    return n[Math.max(0, Math.min(10, Math.floor(mmi + 0.5)))];
  }

  // airbridge.direct_credit
  function directCredit(dist, a) {
    if (dist <= a.road_reach_km) return 1;
    if (dist >= a.forward_max_km) return 0;
    return 1 - (dist - a.road_reach_km) / (a.forward_max_km - a.road_reach_km);
  }

  // airbridge.strip_credit
  function stripCredit(f, a) {
    return f.mmi >= a.zone_min_mmi ? 1 : directCredit(f.dist, a);
  }

  // geo.same_country
  function sameCountry(a, b, aliases) {
    if (!a || !b) return false;
    const al = aliases || {};
    return (al[a] || a) === (al[b] || b);
  }

  // demand.estimate
  function demand(exposure, d) {
    if (!exposure) return null;
    let affected = 0, priority = 0;
    for (const [k, v] of Object.entries(exposure)) {
      const m = +k;
      if (m >= 7) affected += v;
      if (m >= 8) priority += v;
    }
    return { affected, priority, tonnes_per_day: (priority * d.kg_per_person_day) / 1000 };
  }

  // airbridge.build_plan. The damage center and each airfield's MMI and
  // distance are computed in Python and arrive in `event`.
  const NUMERIC_ASSUMPTIONS = ["ops_hours", "shuttle_fleet", "queue_efficiency", "gateway_max_km", "gateway_min_runway_ft",
    "forward_max_km", "zone_min_mmi", "forward_min_runway_ft", "min_usability", "road_reach_km", "min_sorties", "near_tie"];

  function build(event, data, a) {
    // A missing setting would turn comparisons into NaN and quietly produce an empty plan.
    for (const k of NUMERIC_ASSUMPTIONS) if (typeof a[k] !== "number" || Number.isNaN(a[k])) throw new Error(`missing assumption: ${k}`);
    const byName = Object.fromEntries(data.aircraft.map((x) => [x.name, x]));
    const CAP = byName[data.medium_airport_cap], SHUTTLE = byName[data.shuttle.name];
    const curve = data.usability_curve;
    const AL = data.country_aliases || {};
    const country = event.country;

    const fields = event.fields
      .filter((f) => f.dist <= a.gateway_max_km)
      .map((f) => ({
        ...f,
        use: usability(curve, f.mmi),
        in_zone: f.dist <= a.forward_max_km || f.mmi >= a.zone_min_mmi,
        role: "candidate",
      }))
      .sort((x, y) => x.dist - y.dist);

    const dem = demand(event.exposure, data.demand);

    // gateway_candidates
    const gateways = [];
    for (const f of fields) {
      if (f.kind !== "large_airport" && f.kind !== "medium_airport") continue;
      if (f.runway < a.gateway_min_runway_ft || !f.best) continue;
      if (f.use < a.min_usability) continue;
      let ac = byName[f.best];
      if (f.kind === "medium_airport" && ac.payload > CAP.payload) ac = CAP;
      const turns = a.ops_hours / ac.ground;
      const inflow = a.mog_gateway[f.kind] * ac.payload * turns * a.queue_efficiency * f.use;
      gateways.push({ field: f, aircraft: ac, inflow });
    }
    gateways.sort((x, y) => y.inflow - x.inflow);

    // forward_candidates
    const strips = fields.filter(
      (f) =>
        f.in_zone &&
        f.runway >= a.forward_min_runway_ft &&
        f.best &&                                  // long enough, and wide enough for a C-130
        f.use >= a.min_usability &&
        (!a.domestic_only || !country || sameCountry(f.country, country, AL))
    );

    // allocate_shuttles
    function allocate(gw) {
      const legs = [];
      for (const s of strips) {
        if (s.ident === gw.field.ident) continue;
        const credit = stripCredit(s, a);
        if (credit <= 0) continue;
        const leg = haversine(gw.field.lat, gw.field.lon, s.lat, s.lon);
        const cycle = (2 * leg) / data.shuttle.block_kmh + 2 * SHUTTLE.ground;
        const maxSorties = (a.ops_hours / cycle) * a.mog_forward[s.kind] * a.queue_efficiency;
        const perSortie = SHUTTLE.payload * s.use * credit;
        legs.push({ rate: perSortie / cycle, s, leg, cycle, maxSorties, credit, perSortie });
      }
      legs.sort((x, y) => y.rate - x.rate);
      let fleetHours = a.shuttle_fleet * a.ops_hours;
      const out = [];
      for (const l of legs) {
        if (fleetHours <= 1e-9) break;
        const sorties = Math.min(l.maxSorties, fleetHours / l.cycle);
        if (sorties < a.min_sorties) continue;
        fleetHours -= sorties * l.cycle;
        out.push({ field: l.s, leg: l.leg, cycle: l.cycle, sorties, credit: l.credit, tpd: sorties * l.perSortie });
      }
      return out;
    }

    // work_out
    function workOut(gw) {
      const forwards = allocate(gw);
      const forwarded = forwards.reduce((s, f) => s + f.tpd, 0);
      const byRoad = gw.inflow * directCredit(gw.field.dist, a);
      return { gateway: gw, forwards, delivered: Math.min(gw.inflow, byRoad + forwarded) };
    }

    // airbridge.pick: the nearest of the options within near_tie of the best capacity
    function pick(options) {
      options = options.filter((o) => o.delivered > 0);
      if (!options.length) return null;
      const best = Math.max(...options.map((o) => o.delivered));
      const close = options.filter((o) => o.delivered >= best * (1 - a.near_tie));
      close.sort((x, y) => x.gateway.field.dist - y.gateway.field.dist || y.delivered - x.delivered);
      return close[0];
    }

    const options = gateways.map(workOut);
    const bestD = pick(options.filter((o) => sameCountry(o.gateway.field.country, country, AL)));
    const bestF = pick(options.filter((o) => !sameCountry(o.gateway.field.country, country, AL)));
    const chosen = bestD || bestF;
    const alternatives = bestD && bestF ? [bestF] : [];

    const delivered = chosen ? chosen.delivered : 0;
    const people = (delivered * 1000) / data.demand.kg_per_person_day;
    const coverage = dem && dem.tonnes_per_day > 0 ? delivered / dem.tonnes_per_day : null;

    const traps = fields.filter((f) => f.in_zone && f.runway >= a.forward_min_runway_ft && f.best && f.use < a.min_usability);
    const naive = fields.find((f) => f.runway >= a.forward_min_runway_ft && f.best) || null;

    // roles, for the table and the map
    for (const t of traps) t.role = "knocked-out";
    if (chosen) {
      for (const f of chosen.forwards) f.field.role = "forward";
      chosen.gateway.field.role = "gateway";
    }
    for (const alt of alternatives) if (alt.gateway.field.role === "candidate") alt.gateway.field.role = "alternative";

    return { event, country, demand: dem, chosen, alternatives, delivered, people, coverage, traps, naive, fields, candidates: gateways.length, assumptions: a };
  }

  const api = { build, usability, roman, haversine, directCredit, stripCredit, demand, sameCountry };
  root.AirliftModel = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof self !== "undefined" ? self : globalThis);
