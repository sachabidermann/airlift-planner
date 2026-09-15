/* Airlift Planner dashboard. Loads data.json, runs AirliftModel in the browser,
   renders map, KPIs, charts, ledger and scorecard. No framework. */
(function () {
  "use strict";

  const M = window.AirliftModel;
  const $ = (id) => document.getElementById(id);
  const fmtInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const fmt1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const people = (n) => (n >= 1e6 ? `${fmt1.format(n / 1e6)}M` : n >= 1e3 ? `${fmtInt.format(n / 1e3)}k` : fmtInt.format(n));
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  let DATA, events, current, plan, map, layers = [], lastBounds = null;
  let ledgerSort = { key: "dist", desc: false };
  let A = null; // current assumptions

  // ------------------------------------------------------------------ tooltip
  const tip = $("tooltip");
  function showTip(html, x, y) {
    tip.innerHTML = html;
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let left = x + 14, top = y + 14;
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    if (top + h > window.innerHeight - 8) top = y - h - 14;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  }
  function hideTip() { tip.hidden = true; }
  function attachTip(el, html) {
    el.addEventListener("mousemove", (e) => showTip(typeof html === "function" ? html() : html, e.clientX, e.clientY));
    el.addEventListener("mouseleave", hideTip);
  }

  // ------------------------------------------------------------------ assumptions
  function readControls() {
    return {
      ...DATA.defaults,
      shuttle_fleet: +$("c-fleet").value,
      ops_hours: +$("c-ops").value,
      forward_max_km: +$("c-fwd").value,
      min_usability: +$("c-use").value,
      domestic_only: $("c-dom").checked,
    };
  }
  function writeControls(a) {
    $("c-fleet").value = a.shuttle_fleet;
    $("c-ops").value = a.ops_hours;
    $("c-fwd").value = a.forward_max_km;
    $("c-use").value = a.min_usability;
    $("c-dom").checked = a.domestic_only;
    updateControlLabels(a);
  }
  function updateControlLabels(a) {
    $("v-fleet").textContent = `${a.shuttle_fleet} aircraft`;
    $("v-ops").textContent = `${a.ops_hours} h`;
    $("v-fwd").textContent = `${a.forward_max_km} km`;
    $("v-use").textContent = `${Math.round(a.min_usability * 100)}%`;
  }

  // ------------------------------------------------------------------ event selection
  function selectEvent(id, pushHash = true) {
    current = events.find((e) => e.id === id) || events[0];
    $("event-select").value = current.id;
    if (pushHash) history.replaceState(null, "", `#${current.id}`);
    recompute();
  }
  function recompute() {
    A = readControls();
    updateControlLabels(A);
    plan = M.build(current, DATA, A);
    renderEvent();
    renderKpis();
    renderMap();
    renderGateway();
    renderForward();
    renderBars();
    renderCurve();
    renderLedger();
    renderScorecard();
    requestAnimationFrame(() => { map.invalidateSize(); if (lastBounds) map.fitBounds(lastBounds, { padding: [30, 30], maxZoom: 9 }); });
  }

  // ------------------------------------------------------------------ event strip
  function alertBadge(level) {
    if (!level) return "";
    return `<span class="badge badge-${esc(level)}">PAGER ${esc(level)}</span>`;
  }
  function renderEvent() {
    const e = current;
    $("event-title").textContent = e.title;
    const when = new Date(e.time).toUTCString().replace(" GMT", " UTC");
    const kind = e.scenario ? `<span class="badge">USGS scenario, simulated</span>` : e.backtest ? `<span class="badge">Real event, backtest</span>` : `<span class="badge">This week</span>`;
    $("event-meta").innerHTML = [
      `<span>USGS ${esc(e.id)}</span>`,
      e.scenario ? "" : `<span>${esc(when)}</span>`,
      kind,
      alertBadge(e.alert),
      `<span>Shaking: ${esc(e.mmi_source)}</span>`,
      e.exposure_source ? `<span>Exposure: ${esc(e.exposure_source)}</span>` : "",
      e.country ? `<span>Affected country: ${esc(e.country)}</span>` : "",
    ].filter(Boolean).join("");
  }

  // ------------------------------------------------------------------ KPIs
  function kpi(label, value, sub, cls = "") {
    return `<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value ${cls}">${value}</div><div class="kpi-sub">${sub}</div></div>`;
  }
  function renderKpis() {
    const p = plan, d = p.demand, g = p.chosen ? p.chosen.gateway : null;
    let coverage, coverageSub;
    if (p.coverage == null) { coverage = "n/a"; coverageSub = "no PAGER exposure for this event"; }
    else if (p.coverage >= 1) { coverage = "100<small>%</small>"; coverageSub = `capacity is ${fmt1.format(p.coverage)}× need; distribution is the constraint`; }
    else { coverage = `${Math.round(p.coverage * 100)}<small>%</small>`; coverageSub = "rest must come by road, sea or local supply"; }
    $("kpis").innerHTML = [
      kpi("Delivered into zone", `${fmtInt.format(p.delivered)}<small>t/day</small>`, g ? `via ${esc(g.field.ident)}` : "no viable gateway"),
      kpi("People sustained", `${people(p.people)}<small>/day</small>`, `at ${fmt1.format(DATA.demand.kg_per_person_day)} kg per person per day`),
      kpi("Coverage of need", coverage, coverageSub),
      kpi("Priority population", d ? people(d.priority) : "n/a", d ? `MMI VIII+; ${people(d.affected)} at MMI VII+` : "no PAGER exposure"),
      kpi("Daily cargo needed", d ? `${fmtInt.format(d.tonnes_per_day)}<small>t/day</small>` : "n/a", "food, medical, shelter share"),
      kpi("Airfields knocked out", String(p.traps.length), p.traps.length ? esc(p.traps.slice(0, 3).map((t) => t.ident).join(", ")) + (p.traps.length > 3 ? ", …" : "") : "none flagged in the zone"),
    ].join("");
  }

  // ------------------------------------------------------------------ map
  function initMap() {
    map = L.map("map", { zoomControl: true, scrollWheelZoom: false }).setView([0, 0], 2);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors · USGS ShakeMap · OurAirports", maxZoom: 18, opacity: 0.8,
    }).addTo(map);
  }
  // USGS ShakeMap intensity colours, one per whole MMI, blended between.
  const MMI_COLORS = [[255,255,255],[255,255,255],[191,204,255],[160,230,255],[128,255,255],[122,255,147],[255,255,0],[255,200,0],[255,145,0],[255,0,0],[200,0,0]];
  function mmiColor(m) {
    const i = Math.max(0, Math.min(9, Math.floor(m))), t = Math.max(0, Math.min(1, m - i));
    const a = MMI_COLORS[i], b = MMI_COLORS[Math.min(10, i + 1)];
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  }
  function gridImage(g) {
    const c = document.createElement("canvas");
    c.width = g.nx; c.height = g.ny;
    const ctx = c.getContext("2d"), img = ctx.createImageData(g.nx, g.ny);
    for (let iy = 0; iy < g.ny; iy++) {
      for (let ix = 0; ix < g.nx; ix++) {
        const m = g.v[iy * g.nx + ix] / 10;
        const row = g.ny - 1 - iy;                       // grid is south-to-north, canvas is top-down
        const o = (row * g.nx + ix) * 4;
        const [r, gg, b] = mmiColor(m);
        img.data[o] = r; img.data[o + 1] = gg; img.data[o + 2] = b;
        img.data[o + 3] = m < 4.5 ? 0 : Math.round(255 * Math.min(1, (m - 4.5) / 1.5));
      }
    }
    ctx.putImageData(img, 0, 0);
    return c.toDataURL();
  }
  function fieldTip(f, extra) {
    return `<b>${esc(f.ident)} ${esc(f.name)}</b><br>` +
      `<span class="n">MMI ${M.roman(f.mmi)} · ${Math.round(f.use * 100)}% usable · ${fmtInt.format(f.runway)} ft ${esc(f.surface || "")}</span>` +
      `<br><span class="n">${fmtInt.format(f.dist)} km from damage centre</span>${extra ? `<br>${extra}` : ""}`;
  }
  function renderMap() {
    layers.forEach((l) => map.removeLayer(l));
    layers = [];
    const add = (l) => { l.addTo(map); layers.push(l); return l; };
    const e = current, p = plan;
    const bounds = [];
    const col = { gateway: css("--gateway"), forward: css("--forward"), trap: css("--trap"), cand: css("--cand"), ink: css("--ink"), surface: css("--surface") };

    if (e.grid) {
      add(L.imageOverlay(gridImage(e.grid), [[e.grid.y0, e.grid.x0], [e.grid.y1, e.grid.x1]], { opacity: 0.55, interactive: false }));
    } else if (e.contours) {
      add(L.geoJSON(e.contours, { style: (f) => ({ color: f.properties.color, weight: 1.5, opacity: 0.9 }) })
        .bindTooltip((l) => `MMI ${l.feature.properties.value}`, { sticky: true }));
    }
    const forwards = p.chosen ? p.chosen.forwards.filter((f) => f.sorties >= 0.5) : [];
    const forwardIds = new Set(forwards.map((f) => f.field.ident));
    const gwId = p.chosen ? p.chosen.gateway.field.ident : null;
    const altIds = new Set(p.alternatives.map((a) => a.gateway.field.ident));
    const trapIds = new Set(p.traps.map((t) => t.ident));

    for (const f of p.fields) {
      if (f.ident === gwId || altIds.has(f.ident) || forwardIds.has(f.ident) || trapIds.has(f.ident)) continue;
      if (!(f.in_zone || f.dist <= A.forward_max_km * 2)) continue;
      add(L.circleMarker([f.lat, f.lon], { radius: 3, color: col.cand, weight: 1, fillOpacity: 0.6 }).bindTooltip(fieldTip(f)));
    }
    for (const t of p.traps) {
      add(L.circleMarker([t.lat, t.lon], { radius: 7, color: col.trap, weight: 2.5, fillColor: col.surface, fillOpacity: 1 })
        .bindTooltip(fieldTip(t, "likely knocked out")));
      bounds.push([t.lat, t.lon]);
    }
    for (const f of forwards) {
      add(L.circleMarker([f.field.lat, f.field.lon], { radius: 7, color: col.surface, weight: 1.5, fillColor: col.forward, fillOpacity: 1 })
        .bindTooltip(fieldTip(f.field, `forward strip · ${fmtInt.format(f.tpd)} t/day · ${fmt1.format(f.sorties)} sorties`)));
      bounds.push([f.field.lat, f.field.lon]);
    }
    for (const alt of p.alternatives) {
      const f = alt.gateway.field;
      add(L.marker([f.lat, f.lon], { icon: L.divIcon({ className: "", html: '<span class="mk mk-alt"></span>', iconSize: [14, 14], iconAnchor: [7, 7] }) })
        .bindTooltip(fieldTip(f, `alternative gateway · would deliver ${fmtInt.format(alt.delivered)} t/day`)));
      if (f.dist <= A.forward_max_km * 2) bounds.push([f.lat, f.lon]);   // keep the view on the damage zone
    }
    if (p.chosen) {
      const g = p.chosen.gateway.field;
      for (const f of forwards) add(L.polyline([[g.lat, g.lon], [f.field.lat, f.field.lon]], { color: col.gateway, weight: 1, opacity: 0.55, dashArray: "4 4", interactive: false }));
      add(L.marker([g.lat, g.lon], { icon: L.divIcon({ className: "", html: '<span class="mk mk-gateway"></span>', iconSize: [16, 16], iconAnchor: [8, 8] }) })
        .bindTooltip(fieldTip(g, `gateway · ${esc(p.chosen.gateway.aircraft.name)} · ${fmtInt.format(p.chosen.gateway.inflow)} t/day inflow`)));
      bounds.push([g.lat, g.lon]);
    }
    add(L.circleMarker([e.lat, e.lon], { radius: 6, color: col.ink, weight: 2, fillColor: col.ink, fillOpacity: 1 }).bindTooltip("Epicentre"));
    add(L.circleMarker([e.centre[0], e.centre[1]], { radius: 4, color: col.ink, weight: 1.5, fillColor: col.surface, fillOpacity: 1 }).bindTooltip("Damage centre (shaking-weighted)"));
    bounds.push([e.lat, e.lon], e.centre);
    lastBounds = bounds;
    $("map-sub").textContent = `${p.fields.length} candidate airfields within ${fmtInt.format(A.gateway_max_km)} km`;
  }

  // ------------------------------------------------------------------ gateway card
  function renderGateway() {
    const p = plan;
    if (!p.chosen) {
      $("gateway-card").innerHTML = `<div class="card-head"><h2>Gateway</h2></div><div class="empty">No viable gateway airport under these assumptions.</div>`;
      return;
    }
    const g = p.chosen.gateway, f = g.field;
    const rows = [
      ["Airport", `<span class="role-dot role-gateway"></span>${esc(f.ident)} ${esc(f.name)}`, "n wrap"],
      ["Distance to damage centre", `${fmtInt.format(f.dist)} km`],
      ["Shaking · usability", `MMI ${M.roman(f.mmi)} · ${Math.round(f.use * 100)}%`],
      ["Runway", `${fmtInt.format(f.runway)} ft ${esc(f.surface || "")}`],
      ["Heavy aircraft", `${esc(g.aircraft.name)} × ${A.mog_gateway[f.kind]} ramp spots`],
      ["Inflow", `${fmtInt.format(g.inflow)} t/day`],
      ["Reaches zone by road", `${Math.round(M.directCredit(f.dist, A) * 100)}% of inflow`],
    ];
    let html = `<div class="card-head"><h2>Gateway</h2><span class="card-sub">heavy-jet hub</span></div><table class="kv">` +
      rows.map(([k, v, cls]) => `<tr><td class="k">${k}</td><td class="${cls || "n"}">${v}</td></tr>`).join("") + `</table>`;
    if (p.naive && p.naive.ident !== f.ident) {
      html += `<p class="note" style="margin-top:10px">A nearest-airfield rule would pick ${esc(p.naive.ident)} ${esc(p.naive.name)} at ${fmtInt.format(p.naive.dist)} km, MMI ${M.roman(p.naive.mmi)}, ${Math.round(p.naive.use * 100)}% usable.</p>`;
    }
    for (const alt of p.alternatives) {
      const af = alt.gateway.field;
      const kind = af.country !== p.country ? "Foreign" : "Domestic";
      html += `<p class="note" style="margin-top:6px"><span class="role-dot role-alternative"></span>${kind} alternative: ${esc(af.ident)} ${esc(af.name)}, ${fmtInt.format(af.dist)} km, would deliver ${fmtInt.format(alt.delivered)} t/day.</p>`;
    }
    $("gateway-card").innerHTML = html;
  }

  // ------------------------------------------------------------------ forward strips card
  function renderForward() {
    const p = plan;
    const live = p.chosen ? p.chosen.forwards.filter((f) => f.sorties >= 0.5) : [];
    let html = `<div class="card-head"><h2>Forward strips</h2><span class="card-sub">${A.shuttle_fleet} × C-130J, ${A.ops_hours} h/day</span></div>`;
    if (!live.length) { html += `<div class="empty">No forward shuttle legs. ${p.chosen ? "Cargo reaches the zone by road from the gateway." : ""}</div>`; }
    else {
      html += `<table class="strips"><thead><tr><th>Strip</th><th class="n">Leg</th><th class="n">Sorties</th><th class="n">t/day</th></tr></thead><tbody>` +
        live.map((f) => `<tr><td><span class="role-dot role-forward"></span>${esc(f.field.ident)} ${esc(f.field.name)}<span class="sub">MMI ${M.roman(f.field.mmi)} · ${Math.round(f.field.use * 100)}% · ${fmtInt.format(f.field.runway)} ft</span></td>` +
          `<td class="n">${fmtInt.format(f.leg)} km</td><td class="n">${fmt1.format(f.sorties)}</td><td class="n">${fmtInt.format(f.tpd)}</td></tr>`).join("") +
        `</tbody></table>`;
    }
    if (p.traps.length) {
      html += `<h3 style="margin-top:14px">Likely knocked out</h3><table class="strips"><tbody>` +
        p.traps.map((t) => `<tr><td><span class="role-dot role-knocked-out"></span>${esc(t.ident)} ${esc(t.name)}</td><td class="n">${fmtInt.format(t.dist)} km · MMI ${M.roman(t.mmi)} · ${Math.round(t.use * 100)}%</td></tr>`).join("") +
        `</tbody></table>`;
    }
    $("forward-card").innerHTML = html;
  }

  // ------------------------------------------------------------------ bars chart
  function svgEl(tag, attrs, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text != null) el.textContent = text;
    return el;
  }
  function renderBars() {
    const host = $("bars-chart");
    host.innerHTML = "";
    const live = plan.chosen ? plan.chosen.forwards.filter((f) => f.sorties >= 0.5) : [];
    if (!live.length) { host.innerHTML = `<div class="empty">No forward shuttle legs under these assumptions.</div>`; return; }
    const rows = live.slice(0, 12);
    const W = 560, labelW = 190, valW = 56, rowH = 22, padT = 8, padB = 22;
    const H = padT + rows.length * rowH + padB;
    const plotW = W - labelW - valW;
    const max = Math.max(...rows.map((r) => r.tpd));
    const nice = Math.ceil(max / 100) * 100 || 100;
    const x = (v) => labelW + (v / nice) * plotW;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    for (let i = 0; i <= 4; i++) {
      const v = (nice * i) / 4;
      svg.appendChild(svgEl("line", { x1: x(v), x2: x(v), y1: padT, y2: H - padB, class: "grid" }));
      svg.appendChild(svgEl("text", { x: x(v), y: H - 6, "text-anchor": "middle", class: "tick" }, fmtInt.format(v)));
    }
    svg.appendChild(svgEl("line", { x1: labelW, x2: labelW, y1: padT, y2: H - padB, class: "axis" }));
    rows.forEach((r, i) => {
      const y = padT + i * rowH + rowH / 2;
      const label = `${r.field.ident} ${r.field.name}`;
      svg.appendChild(svgEl("text", { x: labelW - 8, y: y + 4, "text-anchor": "end", class: "lab" }, label.length > 30 ? label.slice(0, 29) + "…" : label));
      const w = Math.max(2, x(r.tpd) - labelW);
      svg.appendChild(svgEl("rect", { x: labelW, y: y - 5, width: w, height: 10, rx: 4, fill: css("--forward") }));
      svg.appendChild(svgEl("text", { x: x(r.tpd) + 6, y: y + 4, class: "tick" }, fmtInt.format(r.tpd)));
      const hit = svgEl("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, class: "hit" });
      attachTip(hit, () => fieldTip(r.field, `${fmt1.format(r.sorties)} sorties · ${fmtInt.format(r.leg)} km leg · cycle ${fmt1.format(r.cycle)} h · <b>${fmtInt.format(r.tpd)} t/day</b>`));
      svg.appendChild(hit);
    });
    host.appendChild(svg);
  }

  // ------------------------------------------------------------------ usability curve chart
  function renderCurve() {
    const host = $("curve-chart");
    host.innerHTML = "";
    const W = 560, H = 260, padL = 44, padR = 16, padT = 12, padB = 30;
    const x = (m) => padL + ((m - 3) / 7) * (W - padL - padR);
    const y = (u) => padT + (1 - u) * (H - padT - padB);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    for (let u = 0; u <= 1; u += 0.25) {
      svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y(u), y2: y(u), class: "grid" }));
      svg.appendChild(svgEl("text", { x: padL - 8, y: y(u) + 4, "text-anchor": "end", class: "tick" }, `${Math.round(u * 100)}%`));
    }
    for (let m = 3; m <= 10; m++) {
      svg.appendChild(svgEl("text", { x: x(m), y: H - 10, "text-anchor": "middle", class: "tick" }, M.roman(m)));
    }
    svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y(0), y2: y(0), class: "axis" }));
    svg.appendChild(svgEl("text", { x: W - padR, y: H - 10, "text-anchor": "end", class: "tick" }, ""));
    // threshold line
    svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y(A.min_usability), y2: y(A.min_usability), stroke: css("--trap"), "stroke-width": 1, "stroke-dasharray": "3 3", opacity: 0.7 }));
    svg.appendChild(svgEl("text", { x: padL + 6, y: y(A.min_usability) - 4, "text-anchor": "start", class: "tick" }, `knocked-out threshold ${Math.round(A.min_usability * 100)}%`));
    // curve
    const pts = [];
    for (let m = 3; m <= 10; m += 0.1) pts.push(`${x(m).toFixed(1)},${y(M.usability(DATA.usability_curve, m)).toFixed(1)}`);
    svg.appendChild(svgEl("polyline", { points: pts.join(" "), fill: "none", stroke: css("--ink-2"), "stroke-width": 2 }));
    // airfields
    const shown = plan.fields.filter((f) => f.runway >= A.forward_min_runway_ft && (f.in_zone || f.role !== "candidate" || f.mmi >= 5));
    const color = { gateway: css("--gateway"), alternative: css("--gateway"), forward: css("--forward"), "knocked-out": css("--trap"), candidate: css("--cand") };
    const labelled = [];
    for (const f of shown) {
      const cx = x(Math.max(3, Math.min(10, f.mmi))), cy = y(f.use);
      const isRing = f.role === "knocked-out" || f.role === "alternative";
      const dot = f.role === "gateway"
        ? svgEl("rect", { x: cx - 5, y: cy - 5, width: 10, height: 10, fill: color.gateway, stroke: css("--surface"), "stroke-width": 1.5 })
        : svgEl("circle", { cx, cy, r: f.role === "candidate" ? 3.5 : 5, fill: isRing ? css("--surface") : color[f.role], stroke: isRing ? color[f.role] : css("--surface"), "stroke-width": isRing ? 2 : 1.5, opacity: f.role === "candidate" ? 0.7 : 1 });
      svg.appendChild(dot);
      const hit = svgEl("circle", { cx, cy, r: 9, class: "hit" });
      attachTip(hit, fieldTip(f, f.role === "candidate" ? "" : f.role));
      svg.appendChild(hit);
      if ((f.role === "gateway" || f.role === "knocked-out") && labelled.length < 5) labelled.push({ f, cx, cy });
    }
    // direct labels, nudged apart vertically
    labelled.sort((a, b) => a.cy - b.cy);
    let lastY = -100;
    for (const l of labelled) {
      let ly = Math.max(l.cy - 10, lastY + 13);
      lastY = ly;
      const anchor = l.cx > W - 140 ? "end" : "start";
      svg.appendChild(svgEl("text", { x: l.cx + (anchor === "end" ? -9 : 9), y: ly, "text-anchor": anchor, class: "lab" }, `${l.f.ident} ${Math.round(l.f.use * 100)}%`));
    }
    host.appendChild(svg);
  }

  // ------------------------------------------------------------------ ledger
  const COLS = [
    { key: "role", label: "Role" },
    { key: "ident", label: "Code" },
    { key: "name", label: "Airfield" },
    { key: "country", label: "Country" },
    { key: "kind", label: "Type" },
    { key: "runway", label: "Runway ft", n: true },
    { key: "surface", label: "Surface" },
    { key: "dist", label: "Distance km", n: true },
    { key: "mmi", label: "MMI", n: true },
    { key: "use", label: "Usability", n: true },
    { key: "best", label: "Heavy aircraft" },
  ];
  const ROLE_ORDER = { gateway: 0, alternative: 1, forward: 2, "knocked-out": 3, candidate: 4 };
  const ROLE_LABEL = { gateway: "Gateway", alternative: "Alternative", forward: "Forward strip", "knocked-out": "Knocked out", candidate: "Other" };
  function renderLedgerHead() {
    $("ledger-head").innerHTML = COLS.map((c) =>
      `<th class="sortable ${c.n ? "n" : ""} ${ledgerSort.key === c.key ? "sorted" : ""} ${ledgerSort.key === c.key && ledgerSort.desc ? "desc" : ""}" data-key="${c.key}">${c.label}</th>`).join("");
    $("ledger-head").querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (ledgerSort.key === key) ledgerSort.desc = !ledgerSort.desc; else ledgerSort = { key, desc: key === "use" || key === "runway" || key === "mmi" };
      renderLedger();
    }));
  }
  function renderLedger() {
    renderLedgerHead();
    const q = $("ledger-filter").value.trim().toLowerCase();
    let rows = plan.fields.filter((f) => f.in_zone || f.role !== "candidate" || f.dist <= A.forward_max_km * 2 || (f.kind !== "small_airport" && f.runway >= A.gateway_min_runway_ft && f.dist <= 500));
    if (q) rows = rows.filter((f) => [f.ident, f.name, f.country, ROLE_LABEL[f.role], f.kind].join(" ").toLowerCase().includes(q));
    const k = ledgerSort.key, dir = ledgerSort.desc ? -1 : 1;
    rows.sort((a, b) => {
      let va = k === "role" ? ROLE_ORDER[a.role] : a[k], vb = k === "role" ? ROLE_ORDER[b.role] : b[k];
      if (va == null) va = ""; if (vb == null) vb = "";
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir || a.dist - b.dist;
      return String(va).localeCompare(String(vb)) * dir || a.dist - b.dist;
    });
    $("ledger-count").textContent = `${rows.length} airfields`;
    $("ledger-body").innerHTML = rows.map((f) => `<tr class="hl-${f.role}">` +
      `<td class="role"><span class="role-dot role-${f.role}"></span>${ROLE_LABEL[f.role]}</td>` +
      `<td>${esc(f.ident)}</td><td>${esc(f.name)}</td><td>${esc(f.country)}</td><td>${esc(f.kind.replace("_airport", ""))}</td>` +
      `<td class="n">${fmtInt.format(f.runway)}</td><td>${esc(f.surface || "")}</td><td class="n">${fmtInt.format(f.dist)}</td>` +
      `<td class="n">${M.roman(f.mmi)} <span class="note">(${fmt1.format(f.mmi)})</span></td><td class="n">${Math.round(f.use * 100)}%</td><td>${esc(f.best || "none")}</td></tr>`).join("");
  }

  // ------------------------------------------------------------------ scorecard
  function renderScorecard() {
    const body = $("scorecard-body");
    body.innerHTML = "";
    let hits = 0, total = 0;
    for (const e of events.filter((x) => x.backtest)) {
      const p = e.id === current.id ? plan : M.build(e, DATA, A);
      const flags = p.traps.length ? p.traps.map((t) => `${t.ident}`).join(", ") : "none";
      const gw = p.chosen ? `${p.chosen.gateway.field.ident} ${p.chosen.gateway.field.name}` : "none";
      let matchCell;
      if (!e.actual_ident) { matchCell = `<td class="note">n/a</td>`; }
      else {
        const match = p.chosen && p.chosen.gateway.field.ident === e.actual_ident;
        total++; if (match) hits++;
        matchCell = `<td class="${match ? "match-yes" : "match-no"}">${match ? "Yes" : "No"}</td>`;
      }
      const tr = document.createElement("tr");
      tr.className = e.id === current.id ? "active" : "";
      tr.innerHTML = `<td>${esc(e.name)}</td><td>${esc(flags)}</td><td>${esc(e.closed || "")}</td><td>${esc(gw)}</td><td>${esc(e.actual || "")}</td>${matchCell}`;
      tr.addEventListener("click", () => selectEvent(e.id));
      body.appendChild(tr);
    }
    $("scorecard-note").textContent = `Gateway matches reality in ${hits} of ${total} events where an airlift hub was actually used, under the current assumptions. ` +
      (current.note ? `${current.scenario ? "About this scenario" : "What happened"}: ${current.note}` : "");
  }

  // ------------------------------------------------------------------ method text
  function renderMethod() {
    $("curve-text").textContent = "usability by MMI: " + DATA.usability_curve.map(([m, p]) => `${M.roman(m)} ${Math.round(p * 100)}%`).join(" · ") + " (linear between)";
    const d = DATA.demand;
    $("demand-text").textContent = `${d.food_kg} kg food + ${d.medical_kg} kg medical + ${d.shelter_kit_kg} kg kit ÷ ${d.shelter_kit_people} people ÷ ${d.first_days} days = ${fmt1.format(d.kg_per_person_day)} kg per person per day`;
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    const theme = new URLSearchParams(location.search).get("theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    const res = await fetch("data.json");
    DATA = await res.json();
    events = DATA.events;
    const built = new Date(DATA.built);
    const builtText = `Data built ${built.toISOString().slice(0, 10)}`;
    $("built").textContent = builtText;
    $("foot-built").textContent = `${builtText} · ${events.length} events`;

    const sel = $("event-select");
    const groups = DATA.groups.map(([key, label]) => [label, events.filter((e) => e.group === key)]);
    for (const [label, list] of groups) {
      if (!list.length) continue;
      const og = document.createElement("optgroup");
      og.label = label;
      for (const e of list) { const o = document.createElement("option"); o.value = e.id; o.textContent = e.name; og.appendChild(o); }
      sel.appendChild(og);
    }
    sel.addEventListener("change", () => selectEvent(sel.value));
    $("prev-event").addEventListener("click", () => { const i = events.indexOf(current); selectEvent(events[(i - 1 + events.length) % events.length].id); });
    $("next-event").addEventListener("click", () => { const i = events.indexOf(current); selectEvent(events[(i + 1) % events.length].id); });

    writeControls(DATA.defaults);
    for (const id of ["c-fleet", "c-ops", "c-fwd", "c-use"]) $(id).addEventListener("input", recompute);
    $("c-dom").addEventListener("change", recompute);
    $("reset").addEventListener("click", () => { writeControls(DATA.defaults); recompute(); });
    $("ledger-filter").addEventListener("input", renderLedger);

    renderMethod();
    initMap();
    const hash = location.hash.replace("#", "");
    const landing = events.some((e) => e.id === "gllegacyhaywiredm7p05_se") ? "gllegacyhaywiredm7p05_se" : events[0].id;
    selectEvent(events.some((e) => e.id === hash) ? hash : landing, false);
    window.addEventListener("hashchange", () => { const h = location.hash.replace("#", ""); if (events.some((e) => e.id === h) && h !== current.id) selectEvent(h, false); });
    if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", recompute);
  }

  boot().catch((err) => {
    document.querySelector(".page").innerHTML = `<div class="card"><h2>Could not load data.json</h2><p class="note">${esc(err.message)}. If you opened this file directly, serve the folder instead: <code>python3 -m http.server</code> in docs/.</p></div>`;
  });
})();
