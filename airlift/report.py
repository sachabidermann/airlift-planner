"""Render a plan as terminal text."""

from __future__ import annotations

import math

from .aircraft import SHUTTLE
from .airbridge import Plan
from .demand import NEGLIGIBLE_TPD
from .geo import same_country
from .survivability import roman


def fmt_people(n: float) -> str:
    if n >= 999_500:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return f"{n:.0f}"


def pct(x: float) -> str:
    """Whole percent, rounded down, so 49.7% never prints as 50%."""
    return f"{math.floor(x * 100 + 1e-9)}%"


def render_text(plan: Plan) -> str:
    ev, q, a = plan.event, plan.event.quake, plan.assumptions
    lines = ["", str(q), f"shaking: {ev.mmi_source}" + (f"   PAGER alert: {ev.alert}" if ev.alert else "")]

    lines.append("")
    if not any(f.mmi >= 6 for f in plan.fields):
        lines.append("note: no airfield was shaken above MMI V; little or no airlift need is expected. The plan below is hypothetical.")
    basis = "the epicenter" if plan.center_basis == "epicenter" else f"weighted by {plan.center_basis}"
    lines.append(f"damage center        {plan.center[0]:.2f}, {plan.center[1]:.2f}   ({basis})")
    if plan.demand:
        d = plan.demand
        lines.append(f"exposure source      {ev.exposure.source}")
        lines.append(f"people at MMI VII+   {fmt_people(d.affected):>7}")
        lines.append(f"people at MMI VIII+  {fmt_people(d.priority):>7}   (airbridge priority)")
        if d.tonnes_per_day < NEGLIGIBLE_TPD:
            lines.append(f"cargo needed         under {NEGLIGIBLE_TPD} t/day (negligible)")
        else:
            lines.append(f"cargo needed         {d.tonnes_per_day:>7,.0f} t/day   at {d.kg_per_person_day:.2f} kg per person per day")
    else:
        lines.append("no population exposure data for this event")

    lines.append("")
    if plan.naive_pick:
        n = plan.naive_pick
        lines.append(
            f"nearest airfield     {n.airport.label[:40]:<40} {n.dist_km:>5.0f} km   "
            f"MMI {roman(n.mmi):<4} usable {pct(n.usability)}"
        )
    if plan.traps:
        lines.append("likely knocked out:")
        for t in plan.traps:
            lines.append(
                f"    {t.airport.label[:40]:<40} {t.dist_km:>5.0f} km   MMI {roman(t.mmi):<4} usable {pct(t.usability)}"
            )

    lines.append("")
    if plan.gateway is None and plan.gateway_candidates:
        lines.append(f"no gateway chosen: {plan.gateway_candidates} airports qualify, but none is within {a.forward_max_km:,.0f} km "
                     "of the damage center and no forward strip is usable, so nothing can reach the zone")
    elif plan.gateway is None:
        lines.append(f"no usable gateway: no large or medium airport within {a.gateway_max_km:,.0f} km has a runway of "
                     f"{a.gateway_min_runway_ft:,} ft or more and usability of {pct(a.min_usability)} or more")
    else:
        g = plan.gateway
        lines.append(
            f"GATEWAY   {g.field.airport.label[:44]:<44} {g.field.dist_km:>5.0f} km   "
            f"MMI {roman(g.field.mmi):<4} usable {pct(g.field.usability)}"
        )
        lines.append(
            f"          {g.aircraft.name} x {a.mog_gateway[g.field.airport.kind]} spots, "
            f"{g.field.airport.longest_runway_ft:,} ft   inflow {g.inflow_tpd:,.0f} t/day"
        )
        live = [f for f in plan.forwards if f.sorties_per_day >= 0.5]
        if live:
            lines.append(f"FORWARD   shuttle fleet {a.shuttle_fleet} x {SHUTTLE.name}, airfields open {a.ops_hours:.0f} h/day")
            lines.append(f"          {'strip':<40} {'leg':>6} {'sorties':>8} {'t/day':>7}   MMI")
            for f in live:
                lines.append(
                    f"          {f.field.airport.label[:40]:<40} {f.leg_km:>4.0f}km {f.sorties_per_day:>8.1f} "
                    f"{f.tonnes_per_day:>7.0f}   {roman(f.field.mmi)}"
                )

    for alt in plan.alternatives:
        g = alt.gateway
        kind = "domestic" if same_country(g.field.airport.country, plan.country) else "foreign"
        lines.append(
            f"best {kind} alternative  {g.field.airport.label[:38]:<38} {g.field.dist_km:>5.0f} km   "
            f"capacity {alt.delivered_tpd:,.0f} t/day"
        )

    lines.append("")
    lines.append(f"AIRLIFT CAPACITY INTO ZONE  {plan.delivered_tpd:>7,.0f} t/day   (upper bound; t = metric tons)")
    lines.append(f"people it could supply      {fmt_people(plan.people_sustained):>7}")
    if plan.demand and plan.demand.tonnes_per_day < NEGLIGIBLE_TPD:
        lines.append(f"share of need               {'n/a':>7}   need is negligible")
    elif plan.coverage is not None:
        if plan.coverage >= 1:
            lines.append(f"share of need               {'100%':>7}   capacity is {plan.coverage:.1f}x need; getting it from the airfield to people is the limit")
        else:
            lines.append(f"share of need               {pct(plan.coverage):>7}   the rest must come by road, sea or local supply")
    lines.append("")
    return "\n".join(lines)
