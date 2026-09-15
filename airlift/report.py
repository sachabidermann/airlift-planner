"""Render a plan as terminal text and as a self-contained HTML map."""

from __future__ import annotations

import html
import json
from pathlib import Path

from .airbridge import Plan
from .geo import same_country
from .survivability import roman

OUT_DIR = Path(__file__).resolve().parent.parent / "out"


def _fmt_people(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return f"{n:.0f}"


# --------------------------------------------------------------------------- text


def render_text(plan: Plan) -> str:
    ev, q, a = plan.event, plan.event.quake, plan.assumptions
    lines = ["", str(q), f"shaking data: {ev.mmi_source}" + (f"   PAGER alert: {ev.alert}" if ev.alert else "")]

    lines.append("")
    if not any(f.mmi >= 6 for f in plan.fields):
        lines.append("note: no airfield shaken above MMI V; little or no airlift need is expected. Plan below is hypothetical.")
    lines.append(f"damage centre   {plan.centre[0]:.2f}, {plan.centre[1]:.2f}")
    if plan.demand:
        d = plan.demand
        lines.append(f"people at MMI VII+   {_fmt_people(d.affected):>7}")
        lines.append(f"people at MMI VIII+  {_fmt_people(d.priority):>7}   (airbridge priority)")
        lines.append(f"cargo needed         {d.tonnes_per_day:>7,.0f} t/day   at {d.kg_per_person_day:.2f} kg/person/day")
    else:
        lines.append("no PAGER exposure data for this event")

    lines.append("")
    if plan.naive_pick:
        n = plan.naive_pick
        lines.append(
            f"nearest airfield     {n.airport.label[:40]:<40} {n.dist_km:>5.0f} km   "
            f"MMI {roman(n.mmi):<4} usable {n.usability:.0%}"
        )
    if plan.traps:
        lines.append("likely knocked out:")
        for t in plan.traps:
            lines.append(
                f"    {t.airport.label[:40]:<40} {t.dist_km:>5.0f} km   MMI {roman(t.mmi):<4} usable {t.usability:.0%}"
            )

    lines.append("")
    if plan.gateway is None:
        lines.append("no viable gateway airport found")
    else:
        g = plan.gateway
        lines.append(
            f"GATEWAY   {g.field.airport.label[:44]:<44} {g.field.dist_km:>5.0f} km   "
            f"MMI {roman(g.field.mmi):<4} usable {g.field.usability:.0%}"
        )
        lines.append(
            f"          {g.aircraft.name} x {a.mog_gateway[g.field.airport.kind]} spots, "
            f"{g.field.airport.longest_runway_ft:,} ft   inflow {g.inflow_tpd:,.0f} t/day"
        )
        if plan.forwards:
            lines.append(f"FORWARD   shuttle fleet {a.shuttle_fleet} x C-130J, {a.ops_hours:.0f} h/day")
            lines.append(f"          {'strip':<40} {'leg':>6} {'sorties':>8} {'t/day':>7}   MMI")
            for f in plan.forwards:
                if f.sorties_per_day < 0.5:
                    continue
                lines.append(
                    f"          {f.field.airport.label[:40]:<40} {f.leg_km:>4.0f}km {f.sorties_per_day:>8.1f} "
                    f"{f.tonnes_per_day:>7.0f}   {roman(f.field.mmi)}"
                )

    for alt in plan.alternatives:
        g = alt.gateway
        kind = "domestic" if same_country(g.field.airport.country, plan.country) else "foreign"
        lines.append(
            f"ALT ({kind})  {g.field.airport.label[:38]:<38} {g.field.dist_km:>5.0f} km   "
            f"would deliver {alt.delivered_tpd:,.0f} t/day"
        )

    lines.append("")
    lines.append(f"DELIVERED INTO ZONE  {plan.delivered_tpd:>7,.0f} t/day")
    lines.append(f"people sustained     {_fmt_people(plan.people_sustained):>7}/day")
    if plan.coverage is not None:
        if plan.coverage >= 1:
            lines.append(f"coverage of need        100%   airlift capacity exceeds need ({plan.coverage:.1f}x); distribution is the constraint")
        else:
            lines.append(f"coverage of need     {plan.coverage:>7.0%}   (rest must come by road, sea, or local supply)")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- html


_CSS = """
:root { --ink:#1b1f24; --muted:#5f6b7a; --line:#d9dee5; --bg:#ffffff; --panel:#f5f7fa;
        --gateway:#1f3a93; --forward:#2e7d4f; --trap:#b3261e; --quake:#111111; }
* { box-sizing:border-box; }
body { margin:0; font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color:var(--ink); background:var(--bg); }
#wrap { display:flex; height:100vh; }
#panel { width:400px; min-width:320px; overflow-y:auto; padding:20px 22px; background:var(--panel); border-right:1px solid var(--line); }
#map { flex:1; }
h1 { font-size:17px; font-weight:600; margin:0 0 4px; }
.sub { color:var(--muted); font-size:12px; margin-bottom:16px; }
h2 { font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:18px 0 6px; font-weight:600; }
table { width:100%; border-collapse:collapse; font-size:12.5px; }
td { padding:4px 0; border-bottom:1px solid var(--line); vertical-align:top; }
td.n { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
td.k { color:var(--muted); }
.big { font-size:26px; font-weight:600; font-variant-numeric:tabular-nums; margin:2px 0; }
.big small { font-size:12px; color:var(--muted); font-weight:400; margin-left:6px; }
.tag { display:inline-block; width:10px; height:10px; margin-right:6px; vertical-align:middle; }
.tag.g { background:var(--gateway); } .tag.f { background:var(--forward); border-radius:50%; }
.tag.t { background:var(--trap); border-radius:50%; }
.note { font-size:11.5px; color:var(--muted); line-height:1.45; }
@media (max-width:760px) { #wrap { flex-direction:column; } #panel { width:100%; min-width:0; height:50vh; } #map { height:50vh; } }
"""


def render_html(plan: Plan) -> str:
    ev, q, a = plan.event, plan.event.quake, plan.assumptions
    e = html.escape

    def row(k, v, cls="n"):
        return f"<tr><td class='k'>{e(k)}</td><td class='{cls}'>{v}</td></tr>"

    # ---- panel
    parts = [f"<h1>{e(str(q))}</h1>", f"<div class='sub'>USGS {e(q.id)} · shaking from {e(ev.mmi_source)}"
             + (f" · PAGER alert {e(ev.alert)}" if ev.alert else "") + "</div>"]

    parts.append("<h2>Result</h2>")
    parts.append(f"<div class='big'>{plan.delivered_tpd:,.0f}<small>tonnes/day delivered into the damage zone</small></div>")
    parts.append(f"<div class='big'>{_fmt_people(plan.people_sustained)}<small>people sustained per day</small></div>")
    if plan.coverage is not None:
        if plan.coverage >= 1:
            parts.append(f"<div class='big'>100%<small>of estimated daily need · capacity is {plan.coverage:.1f}× need, distribution is the constraint</small></div>")
        else:
            parts.append(f"<div class='big'>{plan.coverage:.0%}<small>of estimated daily need</small></div>")

    if plan.demand:
        d = plan.demand
        parts.append("<h2>Need</h2><table>")
        parts.append(row("People at MMI VII+", _fmt_people(d.affected)))
        parts.append(row("People at MMI VIII+ (priority)", _fmt_people(d.priority)))
        parts.append(row("Cargo per person per day", f"{d.kg_per_person_day:.2f} kg"))
        parts.append(row("Daily cargo needed", f"{d.tonnes_per_day:,.0f} t"))
        parts.append("</table>")

    if plan.gateway:
        g = plan.gateway
        parts.append("<h2><span class='tag g'></span>Gateway</h2><table>")
        parts.append(row("Airport", e(g.field.airport.label), "n"))
        parts.append(row("Distance to damage centre", f"{g.field.dist_km:,.0f} km"))
        parts.append(row("Shaking / usability", f"MMI {roman(g.field.mmi)} · {g.field.usability:.0%}"))
        parts.append(row("Runway", f"{g.field.airport.longest_runway_ft:,} ft {e(g.field.airport.surface)}"))
        parts.append(row("Heavy aircraft", f"{e(g.aircraft.name)} × {a.mog_gateway[g.field.airport.kind]} spots"))
        parts.append(row("Inflow", f"{g.inflow_tpd:,.0f} t/day"))
        parts.append("</table>")

    live = [f for f in plan.forwards if f.sorties_per_day >= 0.5]
    if live:
        parts.append(f"<h2><span class='tag f'></span>Forward strips · {a.shuttle_fleet} × C-130J</h2><table>")
        for f in live:
            parts.append(
                f"<tr><td>{e(f.field.airport.label[:34])}<br><span class='note'>{f.leg_km:.0f} km leg · MMI {roman(f.field.mmi)} · "
                f"{f.sorties_per_day:.1f} sorties</span></td><td class='n'>{f.tonnes_per_day:,.0f} t/day</td></tr>"
            )
        parts.append("</table>")

    if plan.traps:
        parts.append("<h2><span class='tag t'></span>Likely knocked out</h2><table>")
        for t in plan.traps:
            parts.append(
                f"<tr><td>{e(t.airport.label[:34])}</td><td class='n'>{t.dist_km:.0f} km · MMI {roman(t.mmi)} · {t.usability:.0%}</td></tr>"
            )
        parts.append("</table>")
    if plan.naive_pick and plan.gateway and plan.naive_pick.airport.ident != plan.gateway.field.airport.ident:
        n = plan.naive_pick
        parts.append(
            f"<p class='note'>A nearest-airfield rule would send everything to {e(n.airport.label)} "
            f"({n.dist_km:.0f} km, MMI {roman(n.mmi)}, {n.usability:.0%} usable).</p>"
        )
    for alt in plan.alternatives:
        g = alt.gateway
        kind = "Domestic" if same_country(g.field.airport.country, plan.country) else "Foreign"
        parts.append(
            f"<p class='note'>{kind} alternative: {e(g.field.airport.label)} ({g.field.dist_km:.0f} km) "
            f"would deliver {alt.delivered_tpd:,.0f} t/day.</p>"
        )

    parts.append(
        "<h2>Assumptions</h2><p class='note'>Usability is a judgement curve on shaking intensity, not a fitted model. "
        f"Capacity = ramp spots × ({a.ops_hours:.0f} h ÷ turnaround) × payload × usability. "
        "Demand = people at MMI VIII+ × food, medical and a 7-day shelter kit; water excluded. "
        "Aircraft figures are public planning approximations. Distances are straight-line. "
        "Data: USGS ShakeMap and PAGER, OurAirports.</p>"
    )
    panel = "\n".join(parts)

    # ---- map data
    def pt(f):
        return {
            "lat": f.airport.lat, "lon": f.airport.lon, "label": f.airport.label,
            "mmi": roman(f.mmi), "use": round(f.usability * 100), "rw": f.airport.longest_runway_ft,
        }

    data = {
        "quake": {"lat": q.lat, "lon": q.lon, "title": str(q)},
        "centre": {"lat": plan.centre[0], "lon": plan.centre[1]},
        "gateway": pt(plan.gateway.field) | {"tpd": round(plan.gateway.inflow_tpd)} if plan.gateway else None,
        "forwards": [pt(f.field) | {"tpd": round(f.tonnes_per_day)} for f in live],
        "traps": [pt(t) for t in plan.traps],
        "others": [pt(f) for f in plan.fields
                   if (f.in_zone or f.dist_km <= a.forward_max_km * 2)
                   and f.airport.longest_runway_ft >= a.forward_min_runway_ft][:200],
        "contours": ev.contours,
    }

    js = """
const D = DATA;
const map = L.map('map', {zoomControl:true}).setView([D.quake.lat, D.quake.lon], 7);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {attribution:'&copy; OpenStreetMap contributors · USGS ShakeMap · OurAirports', maxZoom:18, opacity:0.75}).addTo(map);
const bounds = [];
function tip(p, extra){ return `<b>${p.label}</b><br>MMI ${p.mmi} · ${p.use}% usable · ${p.rw.toLocaleString()} ft${extra||''}`; }
if (D.contours) {
  L.geoJSON(D.contours, {style: f => ({color: f.properties.color, weight: 1.5, opacity: 0.9})})
   .bindTooltip(l => 'MMI ' + l.feature.properties.value, {sticky:true}).addTo(map);
}
D.others.forEach(p => { L.circleMarker([p.lat,p.lon],{radius:3,color:'#8a949e',weight:1,fillOpacity:.6}).bindTooltip(tip(p)).addTo(map); });
D.traps.forEach(p => { L.circleMarker([p.lat,p.lon],{radius:7,color:'#b3261e',weight:2,fillColor:'#fff',fillOpacity:1}).bindTooltip(tip(p,'<br>likely knocked out')).addTo(map); bounds.push([p.lat,p.lon]); });
D.forwards.forEach(p => { L.circleMarker([p.lat,p.lon],{radius:7,color:'#2e7d4f',weight:2,fillColor:'#2e7d4f',fillOpacity:.9}).bindTooltip(tip(p,`<br>${p.tpd} t/day`)).addTo(map); bounds.push([p.lat,p.lon]); });
if (D.gateway) {
  const g = D.gateway;
  L.marker([g.lat,g.lon],{icon:L.divIcon({className:'',html:'<div style="width:16px;height:16px;background:#1f3a93;border:2px solid #fff;box-shadow:0 0 0 1px #1f3a93"></div>',iconSize:[16,16],iconAnchor:[8,8]})})
    .bindTooltip(tip(g,`<br>gateway · ${g.tpd} t/day inflow`)).addTo(map);
  D.forwards.forEach(p => L.polyline([[g.lat,g.lon],[p.lat,p.lon]],{color:'#1f3a93',weight:1,opacity:.5,dashArray:'4 4'}).addTo(map));
  bounds.push([g.lat,g.lon]);
}
L.circleMarker([D.quake.lat,D.quake.lon],{radius:6,color:'#111',weight:2,fillColor:'#111',fillOpacity:1}).bindTooltip('epicentre').addTo(map);
L.circleMarker([D.centre.lat,D.centre.lon],{radius:4,color:'#111',weight:1,fillColor:'#fff',fillOpacity:1}).bindTooltip('damage centre').addTo(map);
bounds.push([D.quake.lat,D.quake.lon]);
map.fitBounds(bounds,{padding:[30,30]});
"""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Airlift Planner · {e(q.id)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>{_CSS}</style></head>
<body><div id="wrap"><div id="panel">{panel}</div><div id="map"></div></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>const DATA = {json.dumps(data)};</script>
<script>{js}</script>
</body></html>"""


def write_html(plan: Plan, path: Path | None = None) -> Path:
    path = path or OUT_DIR / f"{plan.event.quake.id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(plan), encoding="utf-8")
    return path
