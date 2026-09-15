# Airlift Planner

**The nearest airport to an earthquake is usually the wrong one. This tool finds the right one, and says how many people it can feed.**

![HayWired scenario, San Francisco Bay Area](docs/haywired.png)

*USGS HayWired scenario: a M7.0 on the Hayward Fault under Oakland. Red rings are airports the model expects to be knocked out (Oakland, San Jose, Hayward, Livermore). The blue square is the recommended gateway, SFO. Colour is USGS shaking intensity.*

## What it does

Given any earthquake, real or one of the USGS's official simulated scenarios, in one command:

1. **Estimates whether each airfield survived.** Shaking intensity at every airport within 1,000 km, read off the USGS ShakeMap grid, turned into a probability the runway can take relief flights. Every mainstream tool ranks by distance, and distance is exactly what gets you a cracked runway.
2. **Sizes the need.** People exposed at intensity VIII and above (from USGS PAGER, or rebuilt from US Census data when PAGER was not run) times a minimum daily ration of food, medicine and shelter.
3. **Designs a two-tier airbridge.** Heavy jets into an undamaged gateway hub, C-130s shuttling the last leg into strips inside the damage zone. Capacity comes from ramp spots and turnaround times, the real bottlenecks, not runway length.
4. **Says how far short you are.** Delivered tonnes per day, people sustained, and the share of need that has to come by road or sea instead.

```
uv run main.py --quake gllegacyhaywiredm7p05_se
```

```
M 7.1  Haywired M7.05 Scenario  (USGS scenario, simulated)
people at MMI VIII+     4.8M   (airbridge priority)
cargo needed           5,250 t/day

likely knocked out:
    KOAK Oakland San Francisco Bay Airport      49 km   MMI X    usable 17%
    KSJC Mineta San Jose International Airpo    24 km   MMI IX   usable 21%
    KHWD Hayward Executive Airport              38 km   MMI IX   usable 25%
    ...

GATEWAY   KSFO San Francisco International Airport        58 km   MMI VI   usable 94%
DELIVERED INTO ZONE    4,866 t/day
coverage of need         93%
```

## Dashboard

`docs/` is a static dashboard that runs the whole model in the browser. Pick a US scenario, a real event or this week's quakes, drag the sliders (shuttle fleet, flying hours, forward radius, knocked-out threshold, domestic only) and the airbridge, the map, the survivability chart, the airfield ledger and the scorecard recompute live. No server, no framework, no keys.

```
uv run dashboard/build.py                      # refresh docs/data.json from USGS and Census
node dashboard/test_model.js                   # browser model must match the Python planner
python3 -m http.server 8766 --directory docs   # then open http://localhost:8766
```

The JavaScript port of the planner is checked against the Python output on every event, to the tonne. Add `?theme=light` or `?theme=dark` to force a theme; the event id in the URL hash links to a specific plan, for example `#wa22sfz01_se`.

## Does it work? Nine real earthquakes, replayed

`uv run backtests/run.py` replays real quakes and compares the plan with what relief operations actually did. Full detail in [backtests/RESULTS.md](backtests/RESULTS.md).

| event | model flags as knocked out | what actually closed | model gateway | gateway actually used | match |
|---|---|---|---|---|---|
| Loma Prieta 1989, M6.9 | none (Oakland 94%) | Oakland main runway, liquefaction | San Francisco | San Francisco | yes |
| Anchorage 2018, M7.1 | none | none; Anchorage reopened same day | Anchorage | Anchorage | yes |
| Ridgecrest 2019, M7.1 | none | China Lake facilities | Mojave | none needed | n/a |
| Puerto Rico 2020, M6.4 | none | none | San Juan | none needed | n/a |
| Haiti 2010, M7.0 | none (Port-au-Prince 63%) | none; tower lost, field saturated | Port-au-Prince | Port-au-Prince | yes |
| Nepal 2015, M7.8 | none (Kathmandu 81%) | none; runway damaged by heavy jets | Kathmandu | Kathmandu | yes |
| Turkey 2023, M7.8 | Hatay, Kahramanmaras | Hatay | Gaziantep | Adana and Incirlik | no |
| Morocco 2023, M6.8 | none | none | Marrakech | Marrakech | yes |
| Myanmar 2025, M7.7 | Mandalay, Nay Pyi Taw, 3 small fields | Mandalay, Nay Pyi Taw | Heho | Yangon | no |

Scorecard: the hub matches reality in five of the seven events where an airlift hub was used. Every airport that closed from shaking was flagged, with one false alarm (Kahramanmaras, 48%). The two misses are worth reading: Loma Prieta's Oakland runway failed from liquefaction, which intensity alone does not capture; and in Turkey and Myanmar the model prefers an intact airport close to the damage while real operations chose a bigger one further away for customs, fuel and handling capacity the model cannot see. Gaziantep did serve as a secondary hub in 2023.

Caveat: the airport table is today's, so replays of older events can offer airports that did not exist at the time. It is noted where it matters.

## What would happen here: six USGS scenarios

The USGS publishes official simulated earthquakes for places that have not had their big one yet. The planner runs on them unchanged.

| scenario | people at MMI VIII+ | model gateway | flagged as knocked out | delivered |
|---|---:|---|---|---|
| HayWired M7.0, Hayward Fault, Bay Area | 4.8M | San Francisco | Oakland, San Jose, Hayward, Livermore, Moffett, 6 more | 4,866 t/day, 93% of need |
| ShakeOut M7.8, southern San Andreas, Los Angeles | 8.3M | Long Beach | San Bernardino, Chino, Palmdale, Palm Springs, 14 more | 5,008 t/day, 55% of need |
| Seattle Fault M7.5 | 2.4M | Whidbey Island NAS | Sea-Tac, Boeing Field, Renton, Bremerton | 2,029 t/day, 78% of need |
| New Madrid M7.7, Memphis | 306k | Memphis | 10 small fields in Arkansas and Missouri | 4,716 t/day, exceeds need |
| Cascadia M9.0, Pacific Northwest | 111k | McChord AFB | none (tsunami not modelled) | 1,554 t/day, exceeds need |
| Puerto Rico Trench M8.5 | 1.6M | San Juan, at 63% | none | 3,276 t/day, exceeds need |

For HayWired, the two scenarios with PAGER (Seattle, New Madrid) use USGS's own population exposure; the others use a Census reconstruction (county and city populations sampled against the shaking grid), which is coarser and says so in the dashboard.

## Prior art, including Palantir

Palantir has worked in disaster response for over a decade: with [Direct Relief during Hurricane Sandy](https://www.directrelief.org/2013/02/palantir-expands-commitment-to-help-improve-disaster-response/), with [Team Rubicon](https://www.prnewswire.com/news-releases/palantir-technologies-creates-clinton-global-initiative-commitment-to-action-partners-with-team-rubicon-and-direct-relief-to-revolutionize-disaster-response-efforts-193074341.html) on the ground after Typhoon Haiyan, and more recently through [AIP for Infrastructure Resiliency and Disaster Response](https://www.palantir.com/partnerships/jacobs/IRDR/) with Jacobs. That work is data integration and operations: fusing an organisation's own inventory, field reports and partner data into one operating picture. It does not, as far as anything public shows, include an airfield-survivability or airbridge-capacity model built from ShakeMap. This project is the kind of domain model that would sit on top of a platform like that, not a substitute for one. The US Air Force and FEMA do airfield assessment by sending teams; the point here is a first estimate in the minutes before any team lands.

## How it works

| step | module | data |
|---|---|---|
| Fetch the quake, its shaking grid, and its population exposure; real events and scenarios | `airlift/usgs.py` | USGS event feed, scenario catalog, ShakeMap, PAGER |
| Rebuild exposure for US scenarios without PAGER | `airlift/population.py` | Census population estimates and Gazetteer centroids |
| Load every airport and runway on Earth | `airlift/airports.py` | OurAirports (public domain) |
| Shaking intensity to runway usability | `airlift/survivability.py` | judgement curve anchored on the events above |
| Population exposure to tonnes per day | `airlift/demand.py` | WFP and Sphere planning figures |
| Gateway choice, shuttle allocation, coverage | `airlift/airbridge.py` | ramp spots, turnaround times, aircraft payloads |
| Terminal report and standalone HTML map | `airlift/report.py` | Leaflet, OpenStreetMap |
| Interactive dashboard | `docs/` | browser port of the planner, checked against Python |

Design choices worth knowing:

- The damage centre is the shaking-weighted centroid of the ShakeMap, not the epicentre. For a 400 km rupture the two are far apart.
- Every candidate gateway is worked out in full. An early version ranked by raw inflow first and lost SFO to a dozen pristine airports hundreds of kilometres away.
- Gateways are preferred inside the affected country; US territories count as domestic. The best foreign alternative is still reported.
- Cargo landing at a gateway counts as delivered in full within 50 km of the damage centre, fading to zero at 150 km. Beyond that it has to fly the last leg.
- Regional airports are capped at C-17 class aircraft. They rarely have the pavement strength or ramp for a C-5 or 747.
- Small quakes with no ShakeMap fall back to a published intensity-vs-distance formula (Allen, Wald and Worden 2012), clearly labelled.

## What it is not

Not an operational tool. The usability curve is judgement, not a fitted model. Aircraft figures are public planning approximations. Distances are straight-line. It knows nothing about liquefaction, tsunami, fuel stocks, customs, handling equipment, weather, airspace or roads. It exists to show that a decision most tools get wrong can be got mostly right with free data and a few honest assumptions.

## Run it

Requires [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/sachabidermann/airlift-planner
cd airlift-planner
uv sync
uv run main.py --list                          # significant quakes this week
uv run main.py --latest                        # plan for the newest one
uv run main.py --quake sclegacyshakeout2full_se   # any USGS event or scenario id
uv run main.py --quake us6000jllz --fleet 24 --forward-km 200
uv run backtests/run.py                        # regenerate every replay and scenario
```

Each plan also writes a standalone map to `out/<event id>.html`.

## Roadmap

- Fit the usability curve properly: every M6.5+ quake since 2000 with a known airport outcome
- Liquefaction susceptibility for runways on fill (Oakland, Sea-Tac, San Juan)
- Tsunami inundation for coastal strips in subduction scenarios
- Road travel time from gateway to damage centre instead of straight-line fading credit
- Helicopter tier for villages without a strip (the whole story in Morocco)
- Fuel and handling proxies for gateway choice, to close the Turkey and Myanmar gaps

## Why I built this

I'm a college freshman interested in decision-support software for defence and humanitarian operations. The pattern is the same in both: a situation, an inventory of assets, physical constraints, and a decision that has to be made fast with imperfect data. This is my first attempt at that pattern, built entirely on public data.
