# Method

How each number is produced, and where each constant comes from. Code references are to `airlift/`.

## 1. Inputs

| input | source | code |
|---|---|---|
| Earthquake location, magnitude, time | USGS event feed and detail records; USGS scenario catalog for simulated events | `usgs.py` |
| Shaking intensity (MMI) on a grid | USGS ShakeMap. Medium-resolution CoverageJSON where it exists, low-resolution next, the legacy `grid.xml` for older products | `usgs.py`, `ShakeGrid` |
| People exposed at each intensity | USGS PAGER. Where PAGER was not run, a reconstruction from US Census files | `usgs.py`, `population.py` |
| Airports and runways | OurAirports `airports.csv` and `runways.csv` | `airports.py` |

MMI at a point is bilinear interpolation between the four surrounding grid cells. A point outside the grid reads MMI I. Grids that cross the 180th meridian use longitudes beyond ±180, so lookups shift the longitude into the grid's range first.

Only large, medium and small airports are used. Heliports, seaplane bases, closed airports, closed runways, and runways whose surface is water, ice or snow are dropped. Each airport keeps its longest remaining runway.

## 2. Airfield usability

`survivability.py` maps MMI at the airfield to the probability that it can take relief flights in the first days. Linear between these points:

| MMI | V | VI | VII | VIII | IX | X |
|---|---|---|---|---|---|---|
| usable | 100% | 97% | 90% | 60% | 30% | 10% |

An airfield below 50% (the "minimum usability" setting) is flagged as likely knocked out. It cannot be a gateway or a forward strip.

This curve is a judgment call. It was set by hand while looking at the five international earthquakes in the backtests (Haiti, Nepal, Turkey, Morocco, Myanmar), so for those the backtests check consistency, not out-of-sample skill. The four US events were added later and the curve was left unchanged. They are an out-of-sample check, but a weak one: none of them closed an airport through shaking, and the one airport damaged by ground failure (Oakland 1989) was missed. The ten airport outcomes are listed in the module docstring.

Published work that should replace it:

- FEMA Hazus Earthquake Model Technical Manual, section 7.7, has fragility curves for airport control towers, terminals and fuel facilities, and says of runways: "Little damage is attributed to ground shaking." Runway damage is a ground-failure problem. That is why this model misses Oakland in 1989, where liquefaction took 3,000 ft of runway at MMI VII. https://www.fema.gov/sites/default/files/documents/fema_hazus-earthquake-model-technical-manual-6-1.pdf
- Roark, Truman and Gould (2000) published an airport functionality curve against peak ground acceleration for the New Madrid region. https://www.iitk.ac.in/nicee/wcee/article/0003.pdf

## 3. Need

`demand.py`. People at MMI VIII or above are the priority population.

    kg per person per day = 0.56 + 0.02 + 19.4 / 5 / 7 = 1.13
    metric tons per day   = priority population x 1.13 / 1000

| constant | value | source |
|---|---|---|
| Food | 0.56 kg per person per day | A 2,100 kcal general ration weighs 550 to 590 g. UNHCR, UNICEF, WFP, WHO, *Food and Nutrition Needs in Emergencies*, Table 2. https://www.who.int/publications/i/item/food-and-nutrition-needs-in-emergencies . 2,100 kcal is the Sphere minimum. |
| Medical | 0.02 kg per person per day | Judgment allowance for trauma supplies. The Interagency Emergency Health Kit works out to about 0.0014 kg, so this is generous. https://www.unicef.org/supply/media/2321/file/Interagency-Emergency-Health-Kits-information-note.pdf |
| Shelter | 19.4 kg per family of five, once, spread over 7 days | IFRC shelter tool kit (11 kg) plus two 4 x 6 m tarpaulins (4.2 kg each). https://itemscatalogue.redcross.int/ |
| Water | excluded | At the Sphere minimum of 15 liters per person per day it is rarely flown at scale. https://spherestandards.org/wp-content/uploads/Sphere-Handbook-2018-EN.pdf |

When need is under 5 t/day the "share of need" figure is not shown.

### Census reconstruction

For US events without PAGER (`population.py`): every incorporated place is a point with its 2023 population, and what is left of each county after subtracting its places is spread over a disc the size of the county. Puerto Rico uses municipio populations. Each point is sampled against the ShakeMap grid and binned by rounded intensity, as PAGER does. A place's people are spread over its land area but never thinner than 1,000 per km². The national total of the points equals the Census county total, and the code checks that on load.

`backtests/VERIFICATION.md`, section 4, runs this method on US events that do have PAGER. At MMI VIII and above it gives 0.87 of PAGER's count for the Seattle Fault scenario and 1.05 for New Madrid. Small counts are unreliable. It counts US residents only and uses 2023 population even for the 1989 replay.

## 4. Damage center

`airbridge.py`, `damage_center`. The mean position weighted by (MMI − 6) and by people: PAGER's city list, or the Census points. Without either, airfields stand in as a land proxy so an offshore rupture is not centered on open water. Without a ShakeMap it is the epicenter. All distances in the plan are straight lines from this point.

## 5. Airbridge

### Throughput

Air Force Pamphlet 10-1403, *Air Mobility Planning Factors* (2018), formula 9.0:

    metric tons per day = parking spots x planning payload x (operating hours / ground time) x 0.85 x usability

The 0.85 is the pamphlet's queuing efficiency. Usability is this model's addition. https://static.e-publishing.af.mil/production/1/af_a3/publication/afpam10-1403/afpam10-1403.pdf

| aircraft | min runway | unpaved | planning payload | ground time | source |
|---|---|---|---|---|---|
| C-130J-30 | 3,000 ft | yes | 16.3 t | 1.75 h | AFPAM Tables 1, 3 (18 short tons), 5 (expedited) |
| A400M | 3,000 ft | yes | 28 t | 2.0 h | Airbus: 37 t maximum. 75% of maximum, the ratio AFPAM implies for the C-17 and C-5M. Ground time is judgment. https://www.airbus.com/en/products-services/defence/military-aircraft/a400m |
| C-17 | 3,500 ft | yes | 59.0 t | 2.25 h | AFPAM Tables 1, 3 (65 short tons), 5 (expedited). USAF fact sheet: runways "as short as 3,500 feet". https://www.af.mil/About-Us/Fact-Sheets/Display/Article/1529726/c-17-globemaster-iii/ |
| C-5M | 6,000 ft | no | 90.7 t | 3.75 h | AFPAM Tables 1, 3 (100 short tons), 5 (expedited) |
| 747-8F | 9,000 ft | no | 100 t | 3.0 h | Boeing airport planning document: 132.6 t maximum structural payload, about 8,500 ft wet landing. 75% of maximum. Ground time is judgment; Boeing's ideal turn is 91 minutes. https://www.boeing.com/content/dam/boeing/v2/airports/acaps/747-8_Rev_D.pdf |

Shuttle legs use the C-130J's AFPAM block speed, 530 km/h.

| assumption | value | basis |
|---|---|---|
| Airfield operating hours | 20 per day | AFPAM tabulates 10, 16 and 24. |
| Gateway parking spots | 6 large, 3 medium, 1 small airport | Judgment. Real ramp plans are not public. Port-au-Prince in 2010 had six unloading spots, which were the bottleneck (Veatch and Goentzel 2018, https://www.emerald.com/jhlscm/article/8/4/430/223654/Feeding-the-bottleneck-airport-congestion-during ). |
| Forward strip parking spots | 3, 2, 1 | Judgment. |
| Shuttle fleet | 12 C-130s | Judgment; a dashboard slider. |
| Medium airports capped at the C-17 | | Judgment: they rarely have the pavement strength or ramp for a C-5 or 747. |

Because parking spots are assumed, capacity is an upper bound. It is not a forecast of what an airlift would deliver.

### Gateway

A gateway candidate is a large or medium airport within 1,000 km of the damage center, with a paved or unpaved runway of 7,000 ft or more that at least one aircraft can use, and usability of at least the minimum. Every candidate is worked out in full and the one that moves the most cargo into the zone wins; ties go to the nearer. Gateways in the affected country are preferred, and US territories count as domestic. A foreign gateway is chosen only if no domestic one can move anything. The best option on the other side is reported as the alternative.

### Zone and road share

An airfield is inside the zone if it is within the forward radius (150 km) of the damage center or was shaken at MMI 6.5 or more.

Cargo landing within 50 km of the damage center counts in full, because trucks can cover that. The share falls in a straight line to zero at the forward radius. The same rule applies to forward strips that were not themselves shaken at MMI 6.5 or more.

    capacity into zone = min(gateway inflow, gateway inflow x road share + shuttle tons)

### Shuttles

Forward strips are airfields inside the zone, in the affected country, with a runway of 3,000 ft or more and usability of at least the minimum.

    round trip hours = 2 x leg km / 530 + 2 x 1.75
    ramp limit       = operating hours / round trip x parking spots x 0.85 sorties per day
    tons per sortie  = 16.3 x usability x road share

The fleet's flight hours (aircraft x operating hours) are handed out to strips in order of tons per flight hour. A strip that would get under half a sortie a day is skipped.

## 6. Fallback intensity formula

When USGS has not published a ShakeMap, `estimate_mmi` uses Allen, Wald and Worden (2012), "Intensity attenuation for active crustal regions", *J. Seismol.* 16:409-433, hypocentral-distance form:

    MMI = 2.085 + 1.428 M − 1.402 ln(sqrt(R² + Rm²))   [+ 0.078 ln(R / 50) when R > 50 km]
    Rm  = −0.209 + 2.042 exp(M − 5)

R is hypocentral distance in km. Fitted for M 5.0 to 7.9 within 300 km. `tests/test_usgs.py` checks the code against the 21-row test table of OpenQuake's independent implementation (https://github.com/gem/oq-engine/blob/master/openquake/hazardlib/gsim/allen_2012_ipe.py). It assumes a point source and no site effects. `backtests/VERIFICATION.md`, section 3, measures its error against ShakeMap: 0.70 intensity units on average across 1,532 airports in nine events. The output says when it is in use.

## 7. What is not modeled

Liquefaction, tsunami, fuel, customs, cargo handling equipment, weather, airspace, road networks, real ramp plans, aircraft availability, and anything about who decides. The airport table and Census population are current, including for replays of older events.
