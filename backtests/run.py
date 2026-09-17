"""Replay real earthquakes and run official USGS scenarios through the planner.

    uv run backtests/run.py

Writes backtests/RESULTS.md and an HTML map per event in out/.
"What happened" notes are from public reporting at the time. Scenario notes
describe the USGS study the shaking comes from.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from airlift.airbridge import build_plan  # noqa: E402
from airlift.airports import load_airports  # noqa: E402
from airlift.population import ensure_exposure  # noqa: E402
from airlift.report import render_text, write_html  # noqa: E402
from airlift.survivability import roman  # noqa: E402
from airlift.usgs import fetch_event  # noqa: E402

# Real events with a known outcome. `actual_ident` is the airport that served
# as the main gateway; None when no airlift was needed.
EVENTS = [
    # ---------------------------------------------------------------- United States
    {
        "id": "nc216859", "name": "Loma Prieta 1989, M6.9 (San Francisco Bay Area)", "group": "us-real",
        "watch": ["KOAK", "KSFO", "KSJC", "KWVI"],
        "closed": "Oakland main runway (liquefaction cracking)",
        "actual": "San Francisco and San Jose both open; relief mostly by road", "actual_ident": "KSFO", "actual_idents": ["KSFO", "KSJC"],
        "happened": (
            'Oakland (KOAK) lost its main runway to liquefaction. San Francisco (KSFO) reopened within hours; San Jose (KSJC) stayed open. Relief moved by road. No PAGER product exists for 1989.'
        ),
    },
    {
        "id": "ak20419010", "name": "Anchorage 2018, M7.1 (Alaska)", "group": "us-real",
        "watch": ["PANC", "PAED", "PAMR"],
        "closed": "none (Anchorage inspected and reopened the same day)",
        "actual": "Anchorage (PANC); no airbridge needed", "actual_ident": "PANC",
        "happened": (
            'Anchorage (PANC) closed for inspection and reopened the same day. Elmendorf (PAED) stayed open. Roads were repaired within days; no airlift was needed.'
        ),
    },
    {
        "id": "ci38457511", "name": "Ridgecrest 2019, M7.1 (California desert)", "group": "us-real",
        "watch": ["KNID", "KIYK", "KEDW"],
        "closed": "China Lake naval air station facilities (runway usable)",
        "actual": "none needed; roads stayed open", "actual_ident": None,
        "happened": (
            'China Lake (KNID) took heavy facility damage. Inyokern (KIYK) stayed open. Highway 395 stayed open; no airlift was needed.'
        ),
    },
    {
        "id": "us70006vll", "name": "Puerto Rico 2020, M6.4 (Guánica)", "group": "us-real",
        "watch": ["TJPS", "TJSJ", "TJBQ"],
        "closed": "none",
        "actual": "none needed; road from San Juan", "actual_ident": None,
        "happened": (
            'No airport closed. Ponce (TJPS) stayed open; supplies came by road from San Juan (TJSJ).'
        ),
    },
    # ---------------------------------------------------------------- International
    {
        "id": "usp000h60h", "name": "Haiti 2010, M7.0", "group": "intl-real",
        "watch": ["MTPP", "MDSD"],
        "closed": "none; Port-au-Prince lost its tower and saturated",
        "actual": "Port-au-Prince (Santo Domingo overflow)", "actual_ident": "MTPP",
        "happened": (
            'Port-au-Prince (MTPP) runway survived but the tower was lost; the US Air Force ran the field and it saturated for days. Santo Domingo (MDSD) took the overflow. No PAGER product exists for this event.'
        ),
    },
    {
        "id": "us20002926", "name": "Nepal 2015, M7.8", "group": "intl-real",
        "watch": ["VNKT", "VNPK"],
        "closed": "none; Kathmandu runway damaged by heavy jets",
        "actual": "Kathmandu", "actual_ident": "VNKT",
        "happened": (
            'Kathmandu (VNKT) was the only gateway and saturated; heavy jets damaged the runway and aircraft over 196 t were banned. Pokhara (VNPK) served light aircraft and helicopters. Pokhara International (NP-0003) opened in 2023 and did not exist at the time.'
        ),
    },
    {
        "id": "us6000jllz", "name": "Turkey 2023, M7.8", "group": "intl-real",
        "watch": ["LTDA", "LTAF", "LTAG", "LTAJ", "LTCN"],
        "closed": "Hatay (runway fractured)",
        "actual": "Adana and Incirlik", "actual_ident": "LTAF",
        "happened": (
            'Hatay (LTDA) runway fractured and closed. Adana (LTAF) and Incirlik (LTAG) became the hubs; Gaziantep (LTAJ) and Kahramanmaras (LTCN) also took flights. Cukurova (LTDB) replaced Adana Sakirpasa in 2024.'
        ),
    },
    {
        "id": "us7000kufc", "name": "Morocco 2023, M6.8", "group": "intl-real",
        "watch": ["GMMX"],
        "closed": "none",
        "actual": "Marrakech", "actual_ident": "GMMX",
        "happened": (
            'Marrakech (GMMX) was undamaged and became the hub. Villages were reached by helicopter and road.'
        ),
    },
    {
        "id": "us7000pn9s", "name": "Myanmar 2025, M7.7", "group": "intl-real",
        "watch": ["VYMD", "VYNT", "VYYY"],
        "closed": "Mandalay and Nay Pyi Taw (towers collapsed)",
        "actual": "Yangon", "actual_ident": "VYYY",
        "happened": (
            'Mandalay (VYMD) and Nay Pyi Taw (VYNT) towers collapsed and both airports closed. Yangon (VYYY), 600 km south, became the entry point. The model prefers a closer regional airport; it does not see customs, fuel or handling capacity.'
        ),
    },
]

# Official USGS simulated earthquakes. No outcome to compare against; the
# value is the plan itself, for places that have not had their big one yet.
SCENARIOS = [
    {
        "id": "gllegacyhaywiredm7p05_se", "name": "HayWired scenario, M7.0 Hayward Fault (San Francisco Bay Area)",
        "group": "us-scenario", "watch": ["KOAK", "KSFO", "KSJC", "KSMF", "KSUU"],
        "happened": (
            'USGS HayWired scenario (2018): M7.05 on the Hayward Fault under the East Bay. Oakland International sits on bay fill beside the fault. Exposure is rebuilt from Census data; PAGER was not run.'
        ),
    },
    {
        "id": "sclegacyshakeout2full_se", "name": "ShakeOut scenario, M7.8 southern San Andreas (Los Angeles)",
        "group": "us-scenario", "watch": ["KLAX", "KONT", "KPSP", "KSBD", "KEDW"],
        "happened": (
            'USGS ShakeOut scenario (2008): M7.8 on the southern San Andreas from the Salton Sea to Lake Hughes. Exposure is rebuilt from Census data.'
        ),
    },
    {
        "id": "gllegacycasc9p0expanded_se", "name": "Cascadia scenario, M9.0 subduction zone (Pacific Northwest)",
        "group": "us-scenario", "watch": ["KSEA", "KPDX", "KGEG", "KEUG", "KOTH"],
        "happened": (
            'USGS Cascadia M9.0 scenario: full-length rupture off Oregon and Washington. Tsunami is not modelled, so coastal strips are optimistic. Exposure is rebuilt from Census data.'
        ),
    },
    {
        "id": "wa22sfz01_se", "name": "Seattle Fault scenario, M7.5 (Seattle)",
        "group": "us-scenario", "watch": ["KSEA", "KBFI", "KPAE", "KTCM", "KPDX"],
        "happened": (
            'Washington Geological Survey and USGS 2022 scenario: M7.5 on the Seattle Fault under the city. Exposure is USGS PAGER.'
        ),
    },
    {
        "id": "nm19fema_m7p7_mt_se", "name": "New Madrid scenario, M7.7 (Memphis)",
        "group": "us-scenario", "watch": ["KMEM", "KJBR", "KLIT", "KBNA", "KSTL"],
        "happened": (
            'FEMA and USGS 2019 scenario: M7.7 on the southern New Madrid fault near Marked Tree, Arkansas. Memphis is about 60 km away. Exposure is USGS PAGER.'
        ),
    },
    {
        "id": "caribe25puertorico_2_se", "name": "Puerto Rico Trench scenario, M8.5 (Caribbean)",
        "group": "us-scenario", "watch": ["TJSJ", "TJBQ", "TJPS", "TJMZ"],
        "happened": (
            'USGS 2025 scenario: M8.5 on the Puerto Rico Trench. Every airport on the island is inside the footprint; Miami is 1,600 km away, beyond the gateway radius. Exposure is a Census approximation by municipio land area.'
        ),
    },
]


def main() -> int:
    airports = load_airports()
    by_ident = {ap.ident: ap for ap in airports}
    md = ["# Backtests and scenarios", "",
          "Real earthquakes replayed through the planner and compared with public reporting of what relief "
          "airlifts actually did, followed by official USGS scenario earthquakes. Generated by `uv run backtests/run.py`.", ""]

    for section, items in (("Real events", EVENTS), ("USGS scenarios", SCENARIOS)):
        md.append(f"# {section}")
        md.append("")
        for ev in items:
            event = ensure_exposure(fetch_event(ev["id"]))
            plan = build_plan(event, airports)
            write_html(plan)
            print(f"===== {ev['name']}")
            print(render_text(plan))

            md.append(f"## {ev['name']}  (`{ev['id']}`)")
            md.append("")
            src = f"Shaking data: {event.mmi_source}. Exposure: {event.exposure.source if event.exposure else 'none'}."
            md.append(src + (f" PAGER alert: {event.alert}." if event.alert else ""))
            md.append("")
            md.append("**What the model saw at the airports that mattered**")
            md.append("")
            md.append("| airport | km to damage centre | MMI | usability |")
            md.append("|---|---:|:-:|---:|")
            lookup = {f.airport.ident: f for f in plan.fields}
            for ident in ev["watch"]:
                f = lookup.get(ident)
                if f is None:
                    ap = by_ident.get(ident)
                    md.append(f"| {ident} {ap.name if ap else ''} | beyond search radius | | |")
                    continue
                md.append(f"| {ident} {f.airport.name} | {f.dist_km:,.0f} | {roman(f.mmi)} | {f.usability:.0%} |")
            md.append("")
            md.append("**Plan**")
            md.append("")
            if plan.gateway:
                g = plan.gateway
                md.append(f"- Gateway: **{g.field.airport.label}**, {g.field.dist_km:,.0f} km, MMI {roman(g.field.mmi)}, inflow {g.inflow_tpd:,.0f} t/day")
            else:
                md.append("- Gateway: none found")
            strips = [f for f in plan.forwards if f.sorties_per_day >= 0.5]
            if strips:
                md.append("- Forward strips: " + ", ".join(f"{f.field.airport.label} ({f.tonnes_per_day:.0f} t/day)" for f in strips[:5]))
            if plan.traps:
                md.append("- Flagged as likely knocked out: " + ", ".join(f"{t.airport.label} (MMI {roman(t.mmi)})" for t in plan.traps))
            for alt in plan.alternatives:
                md.append(f"- Alternative gateway: {alt.gateway.field.airport.label}, {alt.delivered_tpd:,.0f} t/day")
            md.append(f"- Delivered into zone: **{plan.delivered_tpd:,.0f} t/day**, sustaining about {plan.people_sustained:,.0f} people/day"
                      + (f", {min(plan.coverage, 1):.0%} of estimated need" if plan.coverage is not None else ""))
            md.append("")
            md.append("**What happened**" if "actual" in ev else "**About this scenario**")
            md.append("")
            md.append(ev["happened"])
            md.append("")
            md.append(f"Map: `out/{ev['id']}.html`")
            md.append("")

    out = Path(__file__).resolve().parent / "RESULTS.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
