/* Airlift Planner airbridge model, browser port of airlift/airbridge.py.
   Pure functions, no DOM. Numbers must match the Python output for the
   default assumptions; dashboard/test_model.js checks that. */
(function (root) {
  "use strict";

  const R_EARTH = 6371.0;

  function haversine(lat1, lon1, lat2, lon2) {
    const p1 = (lat1 * Math.PI) / 180, p2 = (lat2 * Math.PI) / 180;
    const dp = p2 - p1, dl = ((lon2 - lon1) * Math.PI) / 180;
    const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * R_EARTH * Math.asin(Math.sqrt(a));
  }

  function usability(curve, mmi) {
    if (mmi <= curve[0][0]) return curve[0][1];
    if (mmi >= curve[curve.length - 1][0]) return curve[curve.length - 1][1];
    for (let i = 0; i < curve.length - 1; i++) {
      const [m0, p0] = curve[i], [m1, p1] = curve[i + 1];
      if (m0 <= mmi && mmi <= m1) return p0 + ((p1 - p0) * (mmi - m0)) / (m1 - m0);
    }
    return curve[curve.length - 1][1];
  }

  function roman(mmi) {
    const n = ["-", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
    return n[Math.max(0, Math.min(10, Math.round(mmi)))];
  }

  function directCredit(dist, a) {
    if (dist <= a.road_reach_km) return 1;
    if (dist >= a.forward_max_km) return 0;
    return 1 - (dist - a.road_reach_km) / (a.forward_max_km - a.road_reach_km);
  }

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

  function build(event, data, a) {
    const byName = Object.fromEntries(data.aircraft.map((x) => [x.name, x]));
    const C17 = byName["C-17"], SHUTTLE = byName["C-130J"];
    const curve = data.usability_curve;

    // 1. evaluate airfields under the current assumptions
    const fields = event.fields
      .filter((f) => f.dist <= a.gateway_max_km)
      .map((f) => ({
        ...f,
        use: usability(curve, f.mmi),
        in_zone: f.dist <= a.forward_max_km || f.mmi >= a.zone_min_mmi,
        role: "candidate",
      }))
      .sort((x, y) => x.dist - y.dist);

    const country = event.country;
    const dem = demand(event.exposure, data.demand);

    // 2. gateway candidates
    const gateways = [];
    for (const f of fields) {
      if (f.kind !== "large_airport" && f.kind !== "medium_airport") continue;
      if (f.runway < a.gateway_min_runway_ft || !f.best) continue;
      if (f.use < a.min_usability) continue;
      let ac = byName[f.best];
      if (f.kind === "medium_airport" && ac.payload > C17.payload) ac = C17;
      const inflow = f.use * a.mog_gateway[f.kind] * (a.ops_hours / ac.ground) * ac.payload;
      gateways.push({ field: f, aircraft: ac, inflow });
    }
    gateways.sort((x, y) => y.inflow - x.inflow);

    // 3. forward strips
    const strips = fields.filter(
      (f) =>
        f.in_zone &&
        f.runway >= a.forward_min_runway_ft &&
        f.use >= a.min_usability &&
        (!a.domestic_only || !country || f.country === country)
    );

    function allocate(gw) {
      const legs = [];
      for (const s of strips) {
        if (s.ident === gw.field.ident) continue;
        const leg = haversine(gw.field.lat, gw.field.lon, s.lat, s.lon);
        const cycle = (2 * leg) / SHUTTLE.cruise + 2 * SHUTTLE.ground;
        const maxSorties = (a.ops_hours / cycle) * a.mog_forward[s.kind];
        legs.push({ rate: (SHUTTLE.payload * s.use) / cycle, s, leg, cycle, maxSorties });
      }
      legs.sort((x, y) => y.rate - x.rate);
      let fleetHours = a.shuttle_fleet * a.ops_hours;
      const out = [];
      for (const l of legs) {
        if (fleetHours <= 0) break;
        const sorties = Math.min(l.maxSorties, fleetHours / l.cycle);
        fleetHours -= sorties * l.cycle;
        out.push({ field: l.s, leg: l.leg, cycle: l.cycle, sorties, tpd: sorties * SHUTTLE.payload * l.s.use });
      }
      return out;
    }

    function workOut(gw) {
      const forwards = allocate(gw);
      const forwarded = forwards.reduce((s, f) => s + f.tpd, 0);
      const byRoad = gw.inflow * directCredit(gw.field.dist, a);
      return { gateway: gw, forwards, delivered: Math.min(gw.inflow, byRoad + forwarded) };
    }

    const better = (x, y) => {
      if (!y) return true;
      if (Math.abs(x.delivered - y.delivered) > 1e-9) return x.delivered > y.delivered;
      return x.gateway.field.dist < y.gateway.field.dist;
    };

    const domestic = gateways.filter((g) => g.field.country === country).slice(0, 12);
    const foreign = gateways.filter((g) => g.field.country !== country).slice(0, 8);
    let bestD = null, bestF = null;
    for (const g of domestic) { const o = workOut(g); if (better(o, bestD)) bestD = o; }
    for (const g of foreign) { const o = workOut(g); if (better(o, bestF)) bestF = o; }

    let chosen, alternatives;
    if (bestD && bestD.delivered > 0) { chosen = bestD; alternatives = bestF ? [bestF] : []; }
    else { chosen = bestF; alternatives = bestD ? [bestD] : []; }

    const delivered = chosen ? chosen.delivered : 0;
    const people = (delivered * 1000) / data.demand.kg_per_person_day;
    const coverage = dem && dem.tonnes_per_day > 0 ? delivered / dem.tonnes_per_day : null;

    const traps = fields.filter((f) => f.in_zone && f.runway >= a.forward_min_runway_ft && f.use < a.min_usability);
    const naive = fields.find((f) => f.runway >= a.forward_min_runway_ft) || null;

    // roles for the ledger and the map
    for (const t of traps) t.role = "knocked-out";
    if (chosen) {
      for (const f of chosen.forwards) if (f.sorties >= 0.5) f.field.role = "forward";
      chosen.gateway.field.role = "gateway";
    }
    for (const alt of alternatives) if (alt.gateway.field.role === "candidate") alt.gateway.field.role = "alternative";

    return { event, country, demand: dem, chosen, alternatives, delivered, people, coverage, traps, naive, fields, assumptions: a };
  }

  const api = { build, usability, roman, haversine, directCredit, demand };
  root.AirliftModel = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof self !== "undefined" ? self : globalThis);
