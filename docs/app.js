/* Airlift Planner dashboard. Loads data.json, runs AirliftModel (model.js) in
   the browser, and renders the map, key figures, charts and tables. No framework. */
(function () {
  "use strict";

  const M = window.AirliftModel;
  const $ = (id) => document.getElementById(id);
  const fmtInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const fmt1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const fmt2 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const people = (n) => (n >= 999500 ? `${fmt1.format(n / 1e6)}M` : n >= 1e3 ? `${fmtInt.format(n / 1e3)}k` : fmtInt.format(n));
  const pct = (x) => `${Math.floor(x * 100 + 1e-9)}%`;          // rounded down, so 49.7% never shows as 50%
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  let DATA, events, current, plan, map, layers = [], lastBounds = null, fittedFor = null;
  const gridCache = {};
  let sortState = { key: "dist", desc: false };
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
    tip.style.left = `${Math.max(4, left)}px`;
    tip.style.top = `${Math.max(4, top)}px`;
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
    renderTable();
    renderBacktests();
    requestAnimationFrame(() => {
      map.invalidateSize();
      if (lastBounds && fittedFor !== current.id) {           // fit once per event, not on every slider move
        map.fitBounds(lastBounds, { padding: [30, 30], maxZoom: 9 });
        fittedFor = current.id;
      }
    });
  }

  // ------------------------------------------------------------------ event strip
  function renderEvent() {
    const e = current;
    $("event-title").textContent = e.title;
    const when = new Date(e.time).toUTCString().replace(" GMT", " UTC");
    const kind = e.scenario ? "USGS scenario, simulated" : e.backtest ? "Real event, backtest" : "Recent at build";
    $("event-meta").innerHTML = [
      `<span>USGS ${esc(e.id)}</span>`,
      e.scenario ? "" : `<span>${esc(when)}</span>`,
      `<span class="badge">${kind}</span>`,
      e.alert ? `<span class="badge badge-${esc(e.alert)}">PAGER ${esc(e.alert)}</span>` : "",
      `<span>Shaking: ${esc(e.mmi_source)}</span>`,
      e.exposure_source ? `<span>Exposure: ${esc(e.exposure_source)}</span>` : "",
      e.country ? `<span>Affected country: ${esc(e.country)}</span>` : "",
    ].filter(Boolean).join("");
  }

  // ------------------------------------------------------------------ key figures
  function kpi(label, value, sub) {
    return `<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div><div class="kpi-sub">${sub}</div></div>`;
  }
  function renderKpis() {
    const p = plan, d = p.demand, g = p.chosen ? p.chosen.gateway : null;
    const negligible = d && d.tonnes_per_day < DATA.demand.negligible_tpd;
    let share, shareSub;
    if (!d) { share = "n/a"; shareSub = "no population exposure for this event"; }
    else if (negligible) { share = "n/a"; shareSub = "need is negligible"; }
    else if (p.coverage >= 1) { share = "100<small>%</small>"; shareSub = `capacity is ${fmt1.format(p.coverage)}× need; getting it from the airfield to people is the limit`; }
    else { share = `${Math.floor(p.coverage * 100)}<small>%</small>`; shareSub = "the rest must come by road, sea or local supply"; }
    const quiet = !p.fields.some((f) => f.mmi >= 6);
    $("kpis").innerHTML = [
      kpi("Airlift capacity into zone", `${fmtInt.format(p.delivered)}<small>t/day</small>`,
        !g ? "no usable gateway in range" : p.delivered === 0 ? `${esc(g.field.ident)} is usable, but nothing can reach the zone from it` : `upper bound, via ${esc(g.field.ident)}; t = metric tons`),
      kpi("People it could supply", people(p.people), `at ${fmt2.format(DATA.demand.kg_per_person_day)} kg per person per day`),
      kpi("Share of need", share, shareSub),
      kpi("Priority population", d ? people(d.priority) : "n/a", d ? `at MMI VIII or above; ${people(d.affected)} at VII or above` : "no population exposure"),
      kpi("Daily cargo needed", !d ? "n/a" : negligible ? `under ${DATA.demand.negligible_tpd}<small>t/day</small>` : `${fmtInt.format(d.tonnes_per_day)}<small>t/day</small>`, "food, medical, shelter"),
      kpi("Likely knocked out", String(p.traps.length), p.traps.length ? esc(p.traps.slice(0, 3).map((t) => t.ident).join(", ")) + (p.traps.length > 3 ? ", …" : "") : "no airfield flagged in the zone"),
    ].join("") + (quiet ? `<div class="kpi kpi-note"><div class="kpi-label">Note</div><div class="kpi-sub">No airfield was shaken above MMI V. Little or no airlift need is expected, so this plan is hypothetical.</div></div>` : "");
  }

  // ------------------------------------------------------------------ map
  function initMap() {
    map = L.map("map", { zoomControl: true, scrollWheelZoom: false }).setView([0, 0], 2);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · USGS ShakeMap · OurAirports',
      maxZoom: 18, opacity: 0.8,
    }).addTo(map);
  }
  // USGS ShakeMap intensity colors, one per whole MMI, blended between.
  const MMI_COLORS = [[255,255,255],[255,255,255],[191,204,255],[160,230,255],[128,255,255],[122,255,147],[255,255,0],[255,200,0],[255,145,0],[255,0,0],[200,0,0]];
  function mmiColor(m) {
    const i = Math.max(0, Math.min(9, Math.floor(m))), t = Math.max(0, Math.min(1, m - i));
    const a = MMI_COLORS[i], b = MMI_COLORS[Math.min(10, i + 1)];
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  }
  // The grid is drawn in Web Mercator so it registers with the base map, with
  // bilinear interpolation between cells and 3x upsampling so it is not blocky.
  function gridSample(g, fx, fy) {
    const ix = Math.min(Math.max(Math.floor(fx), 0), g.nx - 2), iy = Math.min(Math.max(Math.floor(fy), 0), g.ny - 2);
    const tx = Math.min(Math.max(fx - ix, 0), 1), ty = Math.min(Math.max(fy - iy, 0), 1);
    const v = g.v;
    const r0 = v[iy * g.nx + ix] * (1 - tx) + v[iy * g.nx + ix + 1] * tx;
    const r1 = v[(iy + 1) * g.nx + ix] * (1 - tx) + v[(iy + 1) * g.nx + ix + 1] * tx;
    return (r0 * (1 - ty) + r1 * ty) / 10;
  }
  function gridImage(g) {
    const UP = 3, W = g.nx * UP, H = g.ny * UP;
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const ctx = c.getContext("2d"), img = ctx.createImageData(W, H);
    const merc = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
    const m0 = merc(g.y0), m1 = merc(g.y1);
    for (let row = 0; row < H; row++) {
      const m = m1 - ((m1 - m0) * (row + 0.5)) / H;                                 // rows are evenly spaced in Mercator
      const lat = ((2 * Math.atan(Math.exp(m)) - Math.PI / 2) * 180) / Math.PI;
      const fy = ((lat - g.y0) / (g.y1 - g.y0)) * (g.ny - 1);
      for (let col = 0; col < W; col++) {
        const fx = ((col + 0.5) / W) * (g.nx - 1);
        const mm = gridSample(g, fx, fy) || 0;                                        // empty cells arrive as null
        const o = (row * W + col) * 4;
        const [r, gg, b] = mmiColor(mm);
        img.data[o] = r; img.data[o + 1] = gg; img.data[o + 2] = b;
        const edge = Math.min(fx, g.nx - 1 - fx, fy, g.ny - 1 - fy) / 5;             // fade at the grid's edge
        img.data[o + 3] = Math.round(255 * (mm < 4.5 ? 0 : Math.min(1, (mm - 4.5) / 1.5) * Math.min(1, Math.max(0, edge))));
      }
    }
    ctx.putImageData(img, 0, 0);
    return c.toDataURL();
  }
  function fieldTip(f, extra) {
    return `<b>${esc(f.ident)} ${esc(f.name)}</b><br>` +
      `<span class="n">MMI ${M.roman(f.mmi)} · ${pct(f.use)} usable · ${fmtInt.format(f.runway)} ft ${esc(f.surface || "")}</span>` +
      `<br><span class="n">${fmtInt.format(f.dist)} km from damage center</span>${extra ? `<br>${extra}` : ""}`;
  }
  function renderMap() {
    layers.forEach((l) => map.removeLayer(l));
    layers = [];
    const add = (l) => { l.addTo(map); layers.push(l); return l; };
    const e = current, p = plan;
    const bounds = [];
    const col = { gateway: css("--gateway"), forward: css("--forward"), trap: css("--trap"), cand: css("--cand"), ink: css("--ink"), surface: css("--surface") };
    // Events near the 180th meridian: draw everything on the same side as the damage center.
    const lon = (x) => { const c = e.center[1]; while (x - c > 180) x -= 360; while (x - c < -180) x += 360; return x; };

    if (e.grid) {
      if (!gridCache[e.id]) gridCache[e.id] = gridImage(e.grid);
      add(L.imageOverlay(gridCache[e.id], [[e.grid.y0, e.grid.x0], [e.grid.y1, e.grid.x1]], { opacity: 0.55, interactive: false }));
    }
    const forwards = p.chosen ? p.chosen.forwards : [];
    const taken = new Set([...forwards.map((f) => f.field.ident), ...p.alternatives.map((a) => a.gateway.field.ident), ...p.traps.map((t) => t.ident)]);
    if (p.chosen) taken.add(p.chosen.gateway.field.ident);

    for (const f of p.fields) {
      if (taken.has(f.ident) || !(f.in_zone || f.dist <= A.forward_max_km * 2)) continue;
      add(L.circleMarker([f.lat, lon(f.lon)], { radius: 3, color: col.cand, weight: 1, fillOpacity: 0.6 }).bindTooltip(fieldTip(f)));
    }
    for (const t of p.traps) {
      add(L.circleMarker([t.lat, lon(t.lon)], { radius: 7, color: col.trap, weight: 2.5, fillColor: col.surface, fillOpacity: 1 })
        .bindTooltip(fieldTip(t, "likely knocked out")));
      bounds.push([t.lat, lon(t.lon)]);
    }
    for (const f of forwards) {
      add(L.circleMarker([f.field.lat, lon(f.field.lon)], { radius: 7, color: col.surface, weight: 1.5, fillColor: col.forward, fillOpacity: 1 })
        .bindTooltip(fieldTip(f.field, `forward strip · ${fmtInt.format(f.tpd)} t/day · ${fmt1.format(f.sorties)} sorties`)));
      bounds.push([f.field.lat, lon(f.field.lon)]);
    }
    for (const alt of p.alternatives) {
      const f = alt.gateway.field;
      add(L.marker([f.lat, lon(f.lon)], { title: `Alternative gateway ${f.ident} ${f.name}`, icon: L.divIcon({ className: "", html: '<span class="mk mk-alt"></span>', iconSize: [14, 14], iconAnchor: [7, 7] }) })
        .bindTooltip(fieldTip(f, `alternative gateway · capacity ${fmtInt.format(alt.delivered)} t/day`)));
      if (f.dist <= A.forward_max_km * 2) bounds.push([f.lat, lon(f.lon)]);          // keep the view on the damage zone
    }
    if (p.chosen) {
      const g = p.chosen.gateway.field;
      for (const f of forwards) add(L.polyline([[g.lat, lon(g.lon)], [f.field.lat, lon(f.field.lon)]], { color: col.gateway, weight: 1, opacity: 0.55, dashArray: "4 4", interactive: false }));
      add(L.marker([g.lat, lon(g.lon)], { title: `Gateway ${g.ident} ${g.name}`, icon: L.divIcon({ className: "", html: '<span class="mk mk-gateway"></span>', iconSize: [16, 16], iconAnchor: [8, 8] }) })
        .bindTooltip(fieldTip(g, `gateway · ${esc(p.chosen.gateway.aircraft.name)} · can receive ${fmtInt.format(p.chosen.gateway.inflow)} t/day`)));
      bounds.push([g.lat, lon(g.lon)]);
    }
    add(L.circleMarker([e.lat, lon(e.lon)], { radius: 6, color: col.ink, weight: 2, fillColor: col.ink, fillOpacity: 1 }).bindTooltip("Epicenter"));
    add(L.circleMarker([e.center[0], e.center[1]], { radius: 4, color: col.ink, weight: 1.5, fillColor: col.surface, fillOpacity: 1 })
      .bindTooltip(`Damage center (weighted by ${esc(e.center_basis)})`));
    bounds.push([e.lat, lon(e.lon)], e.center);
    lastBounds = bounds;
    $("map-sub").textContent = `${p.fields.length} candidate airfields within ${fmtInt.format(A.gateway_max_km)} km of the damage center`;
  }

  // ------------------------------------------------------------------ gateway card
  function renderGateway() {
    const p = plan;
    if (!p.chosen) {
      $("gateway-card").innerHTML = `<div class="card-head"><h2>Gateway</h2></div><div class="empty">No usable gateway: no airport within ${fmtInt.format(A.gateway_max_km)} km has a paved runway of ${fmtInt.format(A.gateway_min_runway_ft)} ft or more and usability of ${pct(A.min_usability)} or more.</div>`;
      return;
    }
    const g = p.chosen.gateway, f = g.field;
    const rows = [
      ["Airport", `<span class="role-dot role-gateway"></span>${esc(f.ident)} ${esc(f.name)}`, "n wrap"],
      ["Distance to damage center", `${fmtInt.format(f.dist)} km`],
      ["Shaking · usability", `MMI ${M.roman(f.mmi)} · ${pct(f.use)}`],
      ["Runway", `${fmtInt.format(f.runway)} ft ${esc(f.surface || "")}`],
      ["Aircraft and parking spots", `${esc(g.aircraft.name)} × ${A.mog_gateway[f.kind]}`],
      ["Can receive", `${fmtInt.format(g.inflow)} t/day`],
      ["Road share", `${Math.round(M.directCredit(f.dist, A) * 100)}% of that reaches the zone by road`, "n wrap"],
    ];
    let html = `<div class="card-head"><h2>Gateway</h2><span class="card-sub">where heavy jets land</span></div><table class="kv">` +
      rows.map(([k, v, cls]) => `<tr><td class="k">${k}</td><td class="${cls || "n"}">${v}</td></tr>`).join("") + `</table>`;
    if (p.naive && p.naive.ident !== f.ident) {
      html += `<p class="note" style="margin-top:10px">A nearest-airfield rule would pick ${esc(p.naive.ident)} ${esc(p.naive.name)}: ${fmtInt.format(p.naive.dist)} km, MMI ${M.roman(p.naive.mmi)}, ${pct(p.naive.use)} usable.</p>`;
    }
    for (const alt of p.alternatives) {
      const af = alt.gateway.field;
      const kind = M.sameCountry(af.country, p.country, DATA.country_aliases) ? "domestic" : "foreign";
      html += `<p class="note" style="margin-top:6px"><span class="role-dot role-alternative"></span>Best ${kind} alternative: ${esc(af.ident)} ${esc(af.name)}, ${fmtInt.format(af.dist)} km, capacity ${fmtInt.format(alt.delivered)} t/day.</p>`;
    }
    $("gateway-card").innerHTML = html;
  }

  // ------------------------------------------------------------------ forward strips card
  function renderForward() {
    const p = plan;
    const live = p.chosen ? p.chosen.forwards : [];
    let html = `<div class="card-head"><h2>Forward strips</h2><span class="card-sub">${A.shuttle_fleet} × ${esc(DATA.shuttle.name)}, airfields open ${A.ops_hours} h/day</span></div>`;
    if (!live.length) { html += `<div class="empty">No shuttle legs. ${p.chosen ? "Cargo reaches the zone by road from the gateway." : ""}</div>`; }
    else {
      html += `<table class="strips"><thead><tr><th>Airfield</th><th class="n">Leg</th><th class="n">Sorties</th><th class="n">t/day</th></tr></thead><tbody>` +
        live.map((f) => `<tr><td><span class="role-dot role-forward"></span>${esc(f.field.ident)} ${esc(f.field.name)}<span class="sub">MMI ${M.roman(f.field.mmi)} · ${pct(f.field.use)} · ${fmtInt.format(f.field.runway)} ft</span></td>` +
          `<td class="n">${fmtInt.format(f.leg)} km</td><td class="n">${fmt1.format(f.sorties)}</td><td class="n">${fmtInt.format(f.tpd)}</td></tr>`).join("") +
        `</tbody></table>`;
    }
    if (p.traps.length) {
      html += `<h3 style="margin-top:14px">Likely knocked out</h3><table class="strips"><tbody>` +
        p.traps.map((t) => `<tr><td><span class="role-dot role-knocked-out"></span>${esc(t.ident)} ${esc(t.name)}</td><td class="n">${fmtInt.format(t.dist)} km · MMI ${M.roman(t.mmi)} · ${pct(t.use)}</td></tr>`).join("") +
        `</tbody></table>`;
    }
    $("forward-card").innerHTML = html;
  }

  // ------------------------------------------------------------------ charts
  function svgEl(tag, attrs, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text != null) el.textContent = text;
    return el;
  }
  function renderBars() {
    const host = $("bars-chart");
    host.innerHTML = "";
    const live = plan.chosen ? plan.chosen.forwards : [];
    if (!live.length) { host.innerHTML = `<div class="empty">No shuttle legs under these assumptions.</div>`; return; }
    const rows = live.slice(0, 12);
    const W = 560, labelW = 190, valW = 56, rowH = 22, padT = 8, padB = 22;
    const H = padT + rows.length * rowH + padB;
    const plotW = W - labelW - valW;
    const nice = Math.ceil(Math.max(...rows.map((r) => r.tpd)) / 40) * 40 || 40;   // quarters land on round numbers
    const x = (v) => labelW + (v / nice) * plotW;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": "Forward strip capacity in metric tons per day" });
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
      svg.appendChild(svgEl("rect", { x: labelW, y: y - 5, width: Math.max(2, x(r.tpd) - labelW), height: 10, rx: 4, fill: css("--forward") }));
      svg.appendChild(svgEl("text", { x: x(r.tpd) + 6, y: y + 4, class: "tick" }, fmtInt.format(r.tpd)));
      const hit = svgEl("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, class: "hit" });
      attachTip(hit, () => fieldTip(r.field, `${fmt1.format(r.sorties)} sorties · ${fmtInt.format(r.leg)} km leg · ${fmt1.format(r.cycle)} h round trip · <b>${fmtInt.format(r.tpd)} t/day</b>`));
      svg.appendChild(hit);
    });
    host.appendChild(svg);
    if (live.length > rows.length) host.insertAdjacentHTML("beforeend", `<div class="note">${live.length - rows.length} more strips are in the table below.</div>`);
  }

  function renderCurve() {
    const host = $("curve-chart");
    host.innerHTML = "";
    const W = 560, H = 260, padL = 44, padR = 16, padT = 12, padB = 30;
    const x = (m) => padL + ((m - 3) / 7) * (W - padL - padR);
    const y = (u) => padT + (1 - u) * (H - padT - padB);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": "Usability against shaking intensity, with this event's airfields plotted" });
    for (let u = 0; u <= 1; u += 0.25) {
      svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y(u), y2: y(u), class: "grid" }));
      svg.appendChild(svgEl("text", { x: padL - 8, y: y(u) + 4, "text-anchor": "end", class: "tick" }, `${Math.round(u * 100)}%`));
    }
    for (let m = 3; m <= 10; m++) svg.appendChild(svgEl("text", { x: x(m), y: H - 10, "text-anchor": "middle", class: "tick" }, M.roman(m)));
    svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y(0), y2: y(0), class: "axis" }));
    svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y(A.min_usability), y2: y(A.min_usability), stroke: css("--trap"), "stroke-width": 1, "stroke-dasharray": "3 3", opacity: 0.7 }));
    svg.appendChild(svgEl("text", { x: padL + 6, y: y(A.min_usability) - 4, "text-anchor": "start", class: "tick" }, `minimum usability ${Math.round(A.min_usability * 100)}%`));
    const pts = [];
    for (let m = 3; m <= 10; m += 0.1) pts.push(`${x(m).toFixed(1)},${y(M.usability(DATA.usability_curve, m)).toFixed(1)}`);
    svg.appendChild(svgEl("polyline", { points: pts.join(" "), fill: "none", stroke: css("--ink-2"), "stroke-width": 2 }));
    const shown = plan.fields.filter((f) => f.runway >= A.forward_min_runway_ft && (f.in_zone || f.role !== "candidate" || f.mmi >= 5));
    const color = { gateway: css("--gateway"), alternative: css("--gateway"), forward: css("--forward"), "knocked-out": css("--trap"), candidate: css("--cand") };
    const labeled = [];
    for (const f of shown) {
      const cx = x(Math.max(3, Math.min(10, f.mmi))), cy = y(f.use);
      const ring = f.role === "knocked-out" || f.role === "alternative";
      svg.appendChild(f.role === "gateway"
        ? svgEl("rect", { x: cx - 5, y: cy - 5, width: 10, height: 10, fill: color.gateway, stroke: css("--surface"), "stroke-width": 1.5 })
        : svgEl("circle", { cx, cy, r: f.role === "candidate" ? 3.5 : 5, fill: ring ? css("--surface") : color[f.role], stroke: ring ? color[f.role] : css("--surface"), "stroke-width": ring ? 2 : 1.5, opacity: f.role === "candidate" ? 0.7 : 1 }));
      const hit = svgEl("circle", { cx, cy, r: 9, class: "hit" });
      attachTip(hit, fieldTip(f, f.role === "candidate" ? "" : f.role.replace("knocked-out", "likely knocked out")));
      svg.appendChild(hit);
      if ((f.role === "gateway" || f.role === "knocked-out") && labeled.length < 5) labeled.push({ f, cx, cy });
    }
    labeled.sort((a, b) => a.cy - b.cy);
    let lastY = -100;
    for (const l of labeled) {
      const ly = Math.max(l.cy - 10, lastY + 13);
      lastY = ly;
      const anchor = l.cx > W - 140 ? "end" : "start";
      svg.appendChild(svgEl("text", { x: l.cx + (anchor === "end" ? -9 : 9), y: ly, "text-anchor": anchor, class: "lab" }, `${l.f.ident} ${pct(l.f.use)}`));
    }
    host.appendChild(svg);
  }

  // ------------------------------------------------------------------ table of all airfields
  const COLS = [
    { key: "role", label: "Role" },
    { key: "ident", label: "Code" },
    { key: "name", label: "Airfield" },
    { key: "country", label: "Country" },
    { key: "kind", label: "Size" },
    { key: "runway", label: "Runway ft", n: true },
    { key: "surface", label: "Surface" },
    { key: "dist", label: "Distance km", n: true },
    { key: "mmi", label: "MMI", n: true },
    { key: "use", label: "Usability", n: true },
    { key: "heavy", label: "Largest aircraft" },
  ];
  const ROLE_ORDER = { gateway: 0, alternative: 1, forward: 2, "knocked-out": 3, candidate: 4 };
  const ROLE_LABEL = { gateway: "Gateway", alternative: "Alternative", forward: "Forward strip", "knocked-out": "Likely knocked out", candidate: "Other" };
  // The model caps medium airports at the C-17; show what it would actually fly.
  const heavy = (f) => !f.best ? "none" : (f.kind === "medium_airport" && ["C-5M", "747-8F"].includes(f.best) ? `${DATA.medium_airport_cap} (capped)` : f.best);

  function renderTable() {
    $("ledger-head").innerHTML = "<tr>" + COLS.map((c) => {
      const on = sortState.key === c.key;
      return `<th class="${c.n ? "n" : ""}" aria-sort="${on ? (sortState.desc ? "descending" : "ascending") : "none"}">` +
        `<button class="th-btn ${on ? "sorted" : ""} ${on && sortState.desc ? "desc" : ""}" data-key="${c.key}">${c.label}</button></th>`;
    }).join("") + "</tr>";
    $("ledger-head").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      const key = b.dataset.key;
      sortState = sortState.key === key ? { key, desc: !sortState.desc } : { key, desc: ["use", "runway", "mmi"].includes(key) };
      renderTable();
      $("ledger-head").querySelector(`button[data-key="${key}"]`).focus();
    }));
    const q = $("ledger-filter").value.trim().toLowerCase();
    let rows = plan.fields.filter((f) => f.in_zone || f.role !== "candidate" || f.dist <= A.forward_max_km * 2 ||
      (f.kind !== "small_airport" && f.runway >= A.gateway_min_runway_ft && f.dist <= 300));
    if (q) rows = rows.filter((f) => [f.ident, f.name, f.country, ROLE_LABEL[f.role], f.kind].join(" ").toLowerCase().includes(q));
    const k = sortState.key, dir = sortState.desc ? -1 : 1;
    const val = (f) => (k === "role" ? ROLE_ORDER[f.role] : k === "heavy" ? heavy(f) : f[k]);
    rows.sort((a, b) => {
      const va = val(a) ?? "", vb = val(b) ?? "";
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir || a.dist - b.dist;
      return String(va).localeCompare(String(vb)) * dir || a.dist - b.dist;
    });
    $("ledger-count").textContent = `${rows.length} airfields`;
    $("ledger-body").innerHTML = rows.map((f) => `<tr class="hl-${f.role}">` +
      `<td class="role"><span class="role-dot role-${f.role}"></span>${ROLE_LABEL[f.role]}</td>` +
      `<td>${esc(f.ident)}</td><td>${esc(f.name)}</td><td>${esc(f.country)}</td><td>${esc(f.kind.replace("_airport", ""))}</td>` +
      `<td class="n">${fmtInt.format(f.runway)}</td><td>${esc(f.surface || "")}</td><td class="n">${fmtInt.format(f.dist)}</td>` +
      `<td class="n">${M.roman(f.mmi)} <span class="note">(${fmt1.format(f.mmi)})</span></td><td class="n">${pct(f.use)}</td><td>${esc(heavy(f))}</td></tr>`).join("");
  }

  // ------------------------------------------------------------------ backtest results
  function renderBacktests() {
    const body = $("scorecard-body");
    body.innerHTML = "";
    let hits = 0, scored = 0;
    for (const e of events.filter((x) => x.backtest)) {
      const p = e.id === current.id ? plan : M.build(e, DATA, A);
      const flags = p.traps.length ? p.traps.map((t) => `${t.ident} (${pct(t.use)})`).join(", ") : "none";
      const gw = p.chosen ? `${p.chosen.gateway.field.ident} ${p.chosen.gateway.field.name}` : "none";
      let match = `<td class="note">n/a</td>`;
      if (e.hub_used.length) {
        const ok = !!p.chosen && e.hub_used.includes(p.chosen.gateway.field.ident);
        scored++; if (ok) hits++;
        match = `<td class="${ok ? "match-yes" : "match-no"}">${ok ? "Yes" : "No"}</td>`;
      }
      const tr = document.createElement("tr");
      if (e.id === current.id) tr.className = "active";
      tr.innerHTML = `<td><a href="#${esc(e.id)}">${esc(e.name)}</a></td><td>${esc(flags)}</td><td>${esc(e.closed || "")}</td><td>${esc(gw)}</td><td>${esc(e.hub_text || "")}</td>${match}`;
      body.appendChild(tr);
    }
    $("scorecard-note").textContent = `Gateway matches in ${hits} of ${scored} earthquakes where a relief gateway was used, under the current assumptions. ` +
      "Events with no relief airlift are not scored on gateway choice. The usability curve was set by hand on the international events, so for those this checks consistency, not out-of-sample skill.";
    const c = current;
    $("event-note").innerHTML = c.note
      ? `<h3 style="margin-top:12px">${c.scenario ? "About this scenario" : "What happened"}</h3><p>${esc(c.note)}</p>` +
        (c.sources && c.sources.length ? `<p>Sources: ${c.sources.map((u, i) => `<a href="${esc(u)}">[${i + 1}]</a>`).join(" ")}</p>` : "")
      : "";
  }

  // ------------------------------------------------------------------ method text, from the data
  function renderMethod() {
    $("curve-text").textContent = "usability by MMI: " + DATA.usability_curve.map(([m, p]) => `${M.roman(m)} ${Math.round(p * 100)}%`).join(" · ") + " (linear between)";
    const d = DATA.demand;
    $("demand-text").textContent = `${d.food_kg} kg food + ${d.medical_kg} kg medical + ${d.shelter_kit_kg} kg shelter kit ÷ ${d.shelter_kit_people} people ÷ ${d.first_days} days = ${fmt2.format(d.kg_per_person_day)} kg per person per day`;
    $("throughput-text").textContent = `t/day = parking spots × planning payload × operating hours ÷ ground time × ${DATA.defaults.queue_efficiency} × usability`;
  }

  // ------------------------------------------------------------------ start
  async function boot() {
    const theme = new URLSearchParams(location.search).get("theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    if (!window.L) throw new Error("the map library (Leaflet, from unpkg.com) did not load");
    const res = await fetch("data.json");
    if (!res.ok) throw new Error(`data.json returned HTTP ${res.status}`);
    DATA = await res.json();
    events = DATA.events;
    const builtText = `Data built ${DATA.built.slice(0, 10)}`;
    $("built").textContent = builtText;
    $("foot-built").textContent = `${builtText} · ${events.length} events`;

    const sel = $("event-select");
    for (const [key, label] of DATA.groups) {
      const list = events.filter((e) => e.group === key);
      if (!list.length) continue;
      const og = document.createElement("optgroup");
      og.label = label;
      for (const e of list) { const o = document.createElement("option"); o.value = e.id; o.textContent = e.name; og.appendChild(o); }
      sel.appendChild(og);
    }
    sel.addEventListener("change", () => selectEvent(sel.value));
    const step = (d) => selectEvent(events[(events.indexOf(current) + d + events.length) % events.length].id);
    $("prev-event").addEventListener("click", () => step(-1));
    $("next-event").addEventListener("click", () => step(1));

    writeControls(DATA.defaults);
    for (const id of ["c-fleet", "c-ops", "c-fwd", "c-use"]) $(id).addEventListener("input", recompute);
    $("c-dom").addEventListener("change", recompute);
    $("reset").addEventListener("click", () => { writeControls(DATA.defaults); recompute(); });
    $("ledger-filter").addEventListener("input", renderTable);

    renderMethod();
    initMap();
    const known = (id) => events.some((e) => e.id === id);
    const hash = () => decodeURIComponent(location.hash.replace("#", ""));
    const landing = known("gllegacyhaywiredm7p05_se") ? "gllegacyhaywiredm7p05_se" : events[0].id;
    selectEvent(known(hash()) ? hash() : landing, false);
    window.addEventListener("hashchange", () => { if (known(hash()) && hash() !== current.id) { selectEvent(hash(), false); window.scrollTo({ top: 0 }); } });
    if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", recompute);
  }

  boot().catch((err) => {
    document.querySelector(".page").innerHTML = `<div class="card"><h2>The dashboard could not start</h2><p class="note">${esc(err.message)}. If you opened this file directly, serve the folder instead: <code>python3 -m http.server 8766 --directory docs</code>.</p></div>`;
  });
})();
