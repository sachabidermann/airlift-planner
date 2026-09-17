"""The earthquakes this project is tested on, with what actually happened and the sources.

Every historical statement here was checked against the linked sources.
`hub_used` lists the airports that served as the main relief gateway. It is
empty when no relief airlift was mounted, and those events are not scored on
gateway choice.
"""

# Real events with a known outcome.
EVENTS = [
    # ------------------------------------------------------------ United States
    {
        "id": "nc216859", "name": "Loma Prieta 1989, M6.9 (San Francisco Bay Area)", "group": "us-real",
        "watch": ["KOAK", "KSFO", "KSJC", "KWVI"],
        "closed": "Oakland main runway cut from 10,000 ft to 7,000 ft by liquefaction",
        "hub_used": [], "hub_text": "none; relief mostly by road",
        "happened": (
            "Oakland (KOAK) lost 3,000 ft of its 10,000 ft main runway to liquefaction and ran on 7,000 ft for a month. "
            "San Francisco (KSFO) reopened the next morning; San Jose (KSJC) reopened after 40 minutes. Relief moved "
            "mostly by road, plus a small military airlift into Watsonville (KWVI). No PAGER product exists for 1989."
        ),
        "sources": [
            "https://abag.ca.gov/sites/default/files/dont_wing_it.pdf",
        ],
    },
    {
        "id": "ak20419010", "name": "Anchorage 2018, M7.1 (Alaska)", "group": "us-real",
        "watch": ["PANC", "PAED", "PAMR"],
        "closed": "none; Anchorage reopened the same day",
        "hub_used": [], "hub_text": "none; no relief airlift mounted",
        "happened": (
            "Anchorage (PANC) evacuated its tower, held arrivals for a few hours and reopened the same day. "
            "Elmendorf (PAED) was taking aircraft within an hour. Roads were repaired within days. No relief airlift was mounted."
        ),
        "sources": [
            "https://alaskapublic.org/news/2018-12-04/post-earthquake-air-traffic-controllers-exiled-from-anchorage-tower-used-a-pickup-truck-instead",
            "https://www.dvidshub.net/news/301967/jber-rocks-after-70-magnitude-earthquake",
            "https://www.washingtonpost.com/transportation/2018/12/07/an-earthquake-created-highway-hellscape-alaska-days-later-road-reopened-good-new/",
        ],
    },
    {
        "id": "ci38457511", "name": "Ridgecrest 2019, M7.1 (California desert)", "group": "us-real",
        "watch": ["KNID", "KIYK", "KEDW"],
        "closed": "China Lake naval air station declared not mission capable",
        "hub_used": [], "hub_text": "none; no relief airlift mounted",
        "happened": (
            "China Lake (KNID) took heavy facility damage and was declared not mission capable. Inyokern (KIYK) stayed open. "
            "Highway 178 was patched overnight and all area roads were open the next day. No relief airlift was mounted."
        ),
        "sources": [
            "https://news.usni.org/2019/07/09/california-earthquakes-leave-naval-station-china-lake-not-mission-capable",
            "https://www.turnto23.com/news/local-news/grand-jury-report-finds-indian-wells-valley-airport-district-is-essential-to-kern-county",
            "https://abc7news.com/ridgecrest-earthquake-damage-map-of-california-how-far-is-from-which-fault-line-on/5381347/",
        ],
    },
    {
        "id": "us70006vll", "name": "Puerto Rico 2020, M6.4 (Guánica)", "group": "us-real",
        "watch": ["TJPS", "TJSJ", "TJBQ"],
        "closed": "none",
        "hub_used": [], "hub_text": "none; no relief airlift mounted",
        "happened": (
            "No airport closed; San Juan (TJSJ), Ponce (TJPS) and Aguadilla (TJBQ) operated normally. Supplies moved by road. "
            "No relief airlift was mounted."
        ),
        "sources": [
            "https://www.fodors.com/world/caribbean/puerto-rico/experiences/news/puerto-rico-earthquakes-what-you-need-to-know-about-traveling-to-puerto-rico-right-now",
            "https://mutualaiddisasterrelief.org/the-powerful-shake/",
        ],
    },
    # ------------------------------------------------------------ International
    {
        "id": "usp000h60h", "name": "Haiti 2010, M7.0", "group": "intl-real",
        "watch": ["MTPP", "MDSD"],
        "closed": "none; Port-au-Prince tower unusable, field saturated",
        "hub_used": ["MTPP"], "hub_text": "Port-au-Prince (Santo Domingo overflow)",
        "happened": (
            "Port-au-Prince (MTPP) runway survived but the tower was unusable. US Air Force combat controllers ran the field, "
            "which saturated for days and turned aircraft away. Santo Domingo (MDSD) took the overflow. "
            "No PAGER product exists for this event."
        ),
        "sources": [
            "https://www.af.mil/News/Article-Display/Article/117884/",
            "https://odihpn.org/en/publication/military-and-humanitarian-cooperation-in-air-operations-in-haiti/",
            "https://www.csmonitor.com/World/Global-News/2010/0115/Haiti-earthquake-Small-Port-au-Prince-airport-strained-by-aid-demand",
            "https://reliefweb.int/report/haiti/earthquake-haiti-wfp-external-situation-report-15-january-2010",
        ],
    },
    {
        "id": "us20002926", "name": "Nepal 2015, M7.8", "group": "intl-real",
        "watch": ["VNKT", "VNPK"],
        "closed": "none; Kathmandu runway later damaged by heavy jets",
        "hub_used": ["VNKT"], "hub_text": "Kathmandu",
        "happened": (
            "Kathmandu (VNKT) was the only international airport and saturated. Heavy jets damaged the runway and aircraft "
            "over 196 metric tons were banned. Indian Air Force helicopters flew from Pokhara (VNPK). Pokhara International "
            "(listed as NP-0003) opened in 2023 and did not exist at the time."
        ),
        "sources": [
            "https://www.npr.org/2015/04/30/403231812/with-only-one-runway-kathmandus-airport-hinders-earthquake-relief",
            "https://www.nbcnews.com/storyline/nepal-earthquake/nepal-earthquake-kathmandu-airport-closes-damaged-runway-big-planes-n352781",
            "https://en.wikipedia.org/wiki/Operation_Maitri",
            "https://kathmandupost.com/gandaki-province/2023/01/01/pokhara-regional-international-airport-inaugurated",
        ],
    },
    {
        "id": "us6000jllz", "name": "Turkey 2023, M7.8", "group": "intl-real",
        "watch": ["LTDA", "LTAF", "LTAG", "LTAJ", "LTCN"],
        "closed": "Hatay (runway fractured, closed six days)",
        "hub_used": ["LTAF", "LTAG"], "hub_text": "Adana and Incirlik",
        "happened": (
            "Hatay (LTDA) runway fractured and closed for six days. Adana (LTAF) and Incirlik (LTAG) were the relief gateways. "
            "Gaziantep (LTAJ) and Kahramanmaras (LTCN) closed to passengers but took relief flights. "
            "Cukurova (LTDB) replaced Adana Sakirpasa in 2024 and did not exist at the time."
        ),
        "sources": [
            "https://www.hurriyetdailynews.com/hatay-airport-reopened-as-runway-repaired-180858",
            "https://www.stripes.com/branches/air_force/2023-02-23/turkey-earthquake-incirlik%C2%A0-9227594.html",
            "https://www.dailysabah.com/turkey/kahramanmaras-hatay-gaziantep-suspend-flights-after-77-earthquake/news",
            "https://en.wikipedia.org/wiki/Adana_%C5%9Eakirpa%C5%9Fa_Airport",
        ],
    },
    {
        "id": "us7000kufc", "name": "Morocco 2023, M6.8", "group": "intl-real",
        "watch": ["GMMX"],
        "closed": "none",
        "hub_used": ["GMMX"], "hub_text": "Marrakech",
        "happened": (
            "Marrakech (GMMX) had no major damage and became the relief gateway. Villages in the High Atlas were reached by helicopter and road."
        ),
        "sources": [
            "https://medias24.com/2023/09/09/infrastructures-aeroportuaires-aucuns-degats-majeurs-le-trafic-se-poursuit-onda/",
            "https://www.atalayar.com/en/articulo/politics/large-deployment-of-the-moroccan-armed-forces-in-the-earthquake-affected-provinces/20230914125838190918.html",
        ],
    },
    {
        "id": "us7000pn9s", "name": "Myanmar 2025, M7.7", "group": "intl-real",
        "watch": ["VYMD", "VYNT", "VYYY", "VYHH"],
        "closed": "Nay Pyi Taw (tower collapsed) and Mandalay (runway, terminal and radar damage), both closed to commercial flights for a week",
        "hub_used": ["VYYY"], "hub_text": "Yangon",
        "happened": (
            "Nay Pyi Taw (VYNT) lost its control tower; Mandalay (VYMD) had runway, terminal and radar damage. Both closed to "
            "commercial flights for a week. Yangon (VYYY), about 530 km south of Mandalay, was the main relief gateway; military relief flights "
            "reached Nay Pyi Taw from 30 March and Mandalay from 1 April."
        ),
        "sources": [
            "https://myanmar-now.org/en/news/collapse-of-control-tower-closes-airport-in-myanmar-capital/",
            "https://elevenmyanmar.com/news/nay-pyi-taw-and-mandalay-international-airports-resume-operations-after-earthquake-disruptions",
            "https://www.globalsecurity.org/wmd/library/news/myanmar/2025/myanmar-250401-india-mea01.htm",
        ],
    },
]

# Official USGS simulated earthquakes. No outcome to compare against.
SCENARIOS = [
    {
        "id": "gllegacyhaywiredm7p05_se", "name": "HayWired scenario, M7.0 Hayward Fault (San Francisco Bay Area)",
        "group": "us-scenario", "watch": ["KOAK", "KSFO", "KSJC", "KSMF", "KSUU"],
        "happened": (
            "USGS HayWired scenario: M7.05 on the Hayward Fault under the East Bay. Exposure is rebuilt from Census data; "
            "PAGER was not run."
        ),
        "sources": ["https://www.usgs.gov/programs/science-application-for-risk-reduction/science/haywired-scenario"],
    },
    {
        "id": "sclegacyshakeout2full_se", "name": "ShakeOut scenario, M7.8 southern San Andreas (Los Angeles)",
        "group": "us-scenario", "watch": ["KLAX", "KONT", "KPSP", "KSBD", "KEDW"],
        "happened": (
            "USGS ShakeOut scenario (2008): M7.8 on the southern San Andreas. Exposure is rebuilt from Census data."
        ),
        "sources": ["https://pubs.usgs.gov/of/2008/1150/"],
    },
    {
        "id": "gllegacycasc9p0expanded_se", "name": "Cascadia scenario, M9.0 subduction zone (Pacific Northwest)",
        "group": "us-scenario", "watch": ["KSEA", "KPDX", "KGEG", "KEUG", "KOTH"],
        "happened": (
            "USGS Cascadia M9.0 scenario. Tsunami is not modeled, so coastal strips are optimistic. "
            "Exposure is rebuilt from Census data."
        ),
        "sources": ["https://earthquake.usgs.gov/scenarios/eventpage/gllegacycasc9p0expanded_se/executive"],
    },
    {
        "id": "wa22sfz01_se", "name": "Seattle Fault scenario, M7.5 (Seattle)",
        "group": "us-scenario", "watch": ["KSEA", "KBFI", "KPAE", "KTCM", "KPDX"],
        "happened": "USGS catalog scenario: M7.5 on the Seattle Fault under the city. Exposure is USGS PAGER.",
        "sources": ["https://earthquake.usgs.gov/scenarios/eventpage/wa22sfz01_se/executive"],
    },
    {
        "id": "nm19fema_m7p7_mt_se", "name": "New Madrid scenario, M7.7 (Memphis)",
        "group": "us-scenario", "watch": ["KMEM", "KJBR", "KLIT", "KBNA", "KSTL"],
        "happened": "USGS catalog scenario: M7.7 on the southern New Madrid fault. Exposure is USGS PAGER.",
        "sources": ["https://earthquake.usgs.gov/scenarios/eventpage/nm19fema_m7p7_mt_se/executive"],
    },
    {
        "id": "caribe25puertorico_2_se", "name": "Puerto Rico Trench scenario, M8.5 (Caribbean)",
        "group": "us-scenario", "watch": ["TJSJ", "TJBQ", "TJPS", "TJMZ"],
        "happened": (
            "USGS catalog scenario: M8.5 on the Puerto Rico Trench. Every airport on the island is inside the footprint and "
            "the mainland is beyond the gateway radius. Exposure is a Census approximation by municipio land area."
        ),
        "sources": ["https://earthquake.usgs.gov/scenarios/eventpage/caribe25puertorico_2_se/executive"],
    },
]
