"""Additional fictional industry worlds for scripts/emit_industry_corpora.py."""

from __future__ import annotations

from typing import Any


def note(*paragraphs: str) -> str:
    return "\n\n".join(p.strip() for p in paragraphs) + "\n"


def gold(qid: str, question: str, answerable: bool, answers: list[str], docs: list[str], notes: str) -> dict[str, Any]:
    return {
        "question_id": qid,
        "question": question,
        "answerable": answerable,
        "answers": answers,
        "supporting_doc_ids": docs,
        "notes": notes,
    }

ORION = {
    "id": "orion-grid",
    "label": "Orion Grid Cooperative",
    "industry": "Rural electric cooperative",
    "group": "Utilities",
    "prefix": "og-",
    "fictional": True,
    "blurb": "A made-up rural co-op in Highline County. Magpie is the 69 kV substation; Saddle is 12.47 kV. 2023 vs 2026 night-rate windows disagree.",
    "examples": [
        "What voltage is Magpie Substation?",
        "When does the 2026 night rate start according to the current tariff card?",
        "What does Orion charge per kWh on the night rate?",
    ],
    "docs": {
        "about": note(
            "Orion Grid Cooperative — about (fictional co-op)",
            "Orion Grid Cooperative is a made-up rural electric co-op serving invented Highline County. It is not a real utility.",
            "Headquarters is 2 Magpie Road. The co-op does not serve Harbor Institute or Northhaven Water pumps under this name.",
        ),
        "magpie-sub": note(
            "Magpie Substation",
            "Magpie Substation is 69 kV. Feeder 12 leaves Magpie toward the grain elevators. Vegetation work on Feeder 12 uses outage code GREY-7.",
            "Magpie is not the 12.47 kV Saddle yard.",
        ),
        "saddle-sub": note(
            "Saddle Substation",
            "Saddle Substation is 12.47 kV. It feeds ranch taps, not Feeder 12. Saddle has no GREY-7 code.",
        ),
        "tariff-2026": note(
            "Retail tariff card — 2026",
            "Night rate window: 21:00-06:00. Day window: 06:00-21:00. The card does not print a cents-per-kWh figure.",
            "This 2026 card supersedes the 2023 night window.",
        ),
        "tariff-2023": note(
            "Retail tariff card — 2023 (superseded)",
            "The 2023 night rate window was 22:00-06:00. Do not use 22:00 as the current start.",
        ),
        "outage-codes": note(
            "Outage code list",
            "GREY-7 means vegetation on Feeder 12. BLUE-2 means a Magpie breaker misoperation. There is no code for Saddle vegetation.",
        ),
        "dispatch": note(
            "Dispatch desk",
            "Dispatch is staffed 24 hours at 2 Magpie Road. After-hours number: 555-3300. Member services (day): 555-3301.",
        ),
        "tree-cycle": note(
            "Vegetation cycle",
            "Feeder 12 is on a three-year trim cycle, next due August 2027. Saddle taps are on a five-year cycle, next due 2029.",
        ),
        "willow-power": note(
            "Willow Power District (sister, not Orion)",
            "Willow Power District is a made-up municipal in the next county. Its night rate starts at 20:00. Willow does not use code GREY-7.",
        ),
        "member-office": note(
            "Member office hours",
            "Walk-in: Monday-Friday 08:00-16:30. Saturday closed. The office does not accept cash after 16:00.",
        ),
        "storm-plan": note(
            "Storm plan excerpt",
            "Priority restore: Magpie Substation, then Feeder 12 grain elevators, then Saddle ranch taps. The plan does not list a generator rental price.",
        ),
        "metering": note(
            "Metering note",
            "Interval meters on Feeder 12 report every 15 minutes. Saddle ranch meters are monthly reads only.",
        ),
        "safety": note(
            "Field safety card",
            "Hot-stick work on Magpie 69 kV requires two qualified persons. Saddle 12.47 kV rubber-glove work is allowed with one observer.",
        ),
        "omitted": note(
            "What this corpus does not contain",
            "Cents per kWh, the board chair's name, and the count of members are omitted on purpose.",
        ),
        "radio": note(
            "Radio channel card",
            "Dispatch uses channel Orion-A. Tree crews on Feeder 12 use Orion-C. Willow Power radios are not listed.",
        ),
        "warehouse": note(
            "Stores warehouse",
            "69 kV insulators live in Cage 1 at Magpie. 12.47 kV cutouts live in Cage 4 at Saddle. The warehouse does not stock water-utility pipe.",
        ),
    },
    "gold": [
        gold("og-001", "What voltage is Magpie Substation?", True, ["69 kV", "69"], ["magpie-sub"], "Saddle is 12.47 kV."),
        gold("og-002", "What voltage is Saddle Substation?", True, ["12.47 kV", "12.47"], ["saddle-sub"], "Near-neighbour."),
        gold("og-003", "When does the 2026 night rate start according to the current tariff card?", True, ["21:00"], ["tariff-2026"], "2023 started 22:00."),
        gold("og-004", "When did the 2023 night rate start?", True, ["22:00"], ["tariff-2023"], "Dated contrast."),
        gold("og-005", "What does outage code GREY-7 mean?", True, ["vegetation on Feeder 12"], ["outage-codes", "magpie-sub"], "Not BLUE-2."),
        gold("og-006", "What is the Orion after-hours dispatch number?", True, ["555-3300"], ["dispatch"], "Not 555-3301."),
        gold("og-007", "When is Feeder 12 next due for a trim?", True, ["August 2027"], ["tree-cycle"], "Saddle is 2029."),
        gold("og-008", "When does Willow Power District's night rate start?", True, ["20:00"], ["willow-power"], "Sister distractor."),
        gold("og-009", "Are Saturday walk-ins open at the Orion member office?", True, ["no", "Saturday closed"], ["member-office"], "Literal."),
        gold("og-010", "What is the second restore priority in the storm plan after Magpie Substation?", True, ["Feeder 12 grain elevators"], ["storm-plan"], "Then Saddle."),
        gold("og-011", "How often do Feeder 12 interval meters report?", True, ["every 15 minutes", "15 minutes"], ["metering"], "Saddle is monthly."),
        gold("og-012", "Which radio channel do Feeder 12 tree crews use?", True, ["Orion-C"], ["radio"], "Dispatch is Orion-A."),
        gold("og-013", "What does Orion charge per kWh on the night rate?", False, [], [], "No cents printed."),
        gold("og-014", "Who is the board chair of Orion Grid Cooperative?", False, [], [], "Name omitted."),
        gold("og-015", "How many members does Orion have?", False, [], [], "Omitted."),
        gold("og-016", "What is the generator rental price in the storm plan?", False, [], [], "No price."),
    ],
}

PORTHAVEN = {
    "id": "porthaven-port",
    "label": "Porthaven Port Authority",
    "industry": "Seaport / marine terminals",
    "group": "Transport",
    "prefix": "pp-",
    "fictional": True,
    "blurb": "A made-up port. Berth 4 is containers; Berth 9 is dry bulk. 2019 vs current pilot windows disagree.",
    "examples": [
        "Which Porthaven berth handles containers?",
        "What is the current flood-tide pilot window at Porthaven?",
        "What do Porthaven stevedores earn per hour?",
    ],
    "docs": {
        "about": note(
            "Porthaven Port Authority — about (fictional port)",
            "Porthaven is a made-up port authority on an invented estuary. It is not a real harbor.",
            "Berth 4 is containers. Berth 9 is dry bulk. Gate 2 is the truck gate.",
        ),
        "berth-4": note(
            "Berth 4 — containers",
            "Berth 4 handles containers only. Gantry cranes G-1 and G-2 are assigned here. Berth 4 does not take grain ships.",
        ),
        "berth-9": note(
            "Berth 9 — dry bulk",
            "Berth 9 handles dry bulk, mainly grain. Shiploader S-3 is here. No container gantry works Berth 9.",
        ),
        "pilot-current": note(
            "Pilotage circular — current (2026)",
            "Flood-tide inbound window: tide +45 minutes. Slack water is not used for deep-draft container ships.",
            "This circular supersedes the 2019 +20 minute note.",
        ),
        "pilot-2019": note(
            "Pilotage circular — 2019 (superseded)",
            "The 2019 circular used a flood-tide inbound window of tide +20 minutes. That window is withdrawn.",
        ),
        "gate-2": note(
            "Gate 2 truck hours",
            "Gate 2: 05:00-21:00 daily. Reefer plugs are in Yard C, not at Gate 2. After 21:00 trucks wait at the holding pad.",
        ),
        "tugs": note(
            "Tug roster",
            "Tug Bramble and tug Cinder are on the Porthaven roster. There is no tug named Storm Petrel here (that name belongs to another world).",
        ),
        "tide-board": note(
            "Tide board example day",
            "Example posted high water: 03.2 meters at 14:10 local. The board does not convert to a cargo tonnage forecast.",
        ),
        "lark-terminal": note(
            "Lark Private Terminal (sister, not the authority)",
            "Lark Private Terminal is a made-up adjacent dock. Its gate opens 07:00-19:00. Lark is not Berth 4.",
        ),
        "safety": note(
            "Quay safety card",
            "Hard hats on Berth 9 during loader swings. Berth 4 requires high-vis at all times. The card lists no injury statistics.",
        ),
        "rail": note(
            "Port rail note",
            "Unit grain trains use Track 9 behind Berth 9. Container rail uses Track 4. There is no passenger platform.",
        ),
        "contacts": note(
            "Port contacts",
            "Harbor master: 555-4400. Gate 2 clerk: 555-4401. Email: ops@porthaven-port.example",
            "Commissioner names are omitted.",
        ),
        "weather-limit": note(
            "Wind limit card",
            "Gantry operations stop at 22 m/s sustained. Shiploader S-3 stops at 18 m/s. The card does not list a fog visibility number.",
        ),
        "omitted": note(
            "What this corpus does not contain",
            "Stevedore wages, bunker prices, and the port director's name are omitted on purpose.",
        ),
        "customs-shed": note(
            "Customs shed hours",
            "Shed hours: 08:00-16:00 weekdays. The shed does not examine bulk grain at Berth 9; that stays on the ship.",
        ),
        "pilot-office": note(
            "Pilot office",
            "The pilot office is above Gate 2. Inbound deep-draft jobs file 24 hours ahead. The office does not quote a pilotage invoice amount.",
        ),
    },
    "gold": [
        gold("pp-001", "Which Porthaven berth handles containers?", True, ["Berth 4"], ["about", "berth-4"], "Berth 9 is bulk."),
        gold("pp-002", "Which berth handles dry bulk at Porthaven?", True, ["Berth 9"], ["about", "berth-9"], "Near-neighbour."),
        gold("pp-003", "What is the current flood-tide inbound pilot window at Porthaven?", True, ["tide +45 minutes", "+45 minutes"], ["pilot-current"], "2019 was +20."),
        gold("pp-004", "What flood-tide inbound window did the 2019 circular use?", True, ["tide +20 minutes", "+20 minutes"], ["pilot-2019"], "Dated."),
        gold("pp-005", "What are Gate 2 truck hours?", True, ["05:00-21:00"], ["gate-2"], "Not Lark 07:00-19:00."),
        gold("pp-006", "Which gantry cranes are assigned to Berth 4?", True, ["G-1 and G-2", "G-1", "G-2"], ["berth-4"], "Not S-3."),
        gold("pp-007", "At what sustained wind do gantry operations stop?", True, ["22 m/s"], ["weather-limit"], "Shiploader is 18 m/s."),
        gold("pp-008", "What is the harbor master phone number?", True, ["555-4400"], ["contacts"], "Not 555-4401."),
        gold("pp-009", "What are Lark Private Terminal gate hours?", True, ["07:00-19:00"], ["lark-terminal"], "Sister."),
        gold("pp-010", "Which rail track do unit grain trains use?", True, ["Track 9"], ["rail"], "Containers use Track 4."),
        gold("pp-011", "Where are reefer plugs?", True, ["Yard C"], ["gate-2"], "Not Gate 2."),
        gold("pp-012", "What example high water is posted on the tide board?", True, ["03.2 meters at 14:10", "03.2 meters"], ["tide-board"], "Example day."),
        gold("pp-013", "What do Porthaven stevedores earn per hour?", False, [], [], "Wages omitted."),
        gold("pp-014", "Who is the port director?", False, [], [], "Name omitted."),
        gold("pp-015", "What is the bunker fuel price at Porthaven?", False, [], [], "Omitted."),
        gold("pp-016", "What fog visibility limit is on the wind limit card?", False, [], [], "No fog number."),
    ],
}

NIMBUS = {
    "id": "nimbus-seed",
    "label": "Nimbus Seed Bank",
    "industry": "Plant genetic resources",
    "group": "Agriculture",
    "prefix": "ns-",
    "fictional": True,
    "blurb": "A made-up genebank on the Palouse. Accession NB-1882 is barley; NW-4401 is wheat. 2022 vs 2025 viability scores disagree.",
    "examples": [
        "Which crop is accession NB-1882?",
        "What viability did the 2025 test report for NB-1882?",
        "How much does a commercial packet of NB-1882 cost?",
    ],
    "docs": {
        "about": note(
            "Nimbus Seed Bank — about (fictional genebank)",
            "Nimbus Seed Bank is a made-up genebank on an invented Palouse station. It is not a real CGIAR center.",
            "Barley accessions use the NB- prefix. Wheat accessions use the NW- prefix.",
        ),
        "nb-1882": note(
            "Accession NB-1882",
            "NB-1882 is six-row barley. Origin listed as Highline benches (invented). It is not wheat. Cold-room tray color is blue.",
        ),
        "nw-4401": note(
            "Accession NW-4401",
            "NW-4401 is hard red wheat. Tray color is yellow. It is not barley and is not stored in the blue trays.",
        ),
        "viability-2025": note(
            "Viability tests — 2025",
            "NB-1882 germination: 94%. NW-4401 germination: 88%. Tests run at 20 C for 7 days.",
        ),
        "viability-2022": note(
            "Viability tests — 2022 (superseded for NB-1882)",
            "The 2022 test listed NB-1882 germination 81%. That score is replaced by the 2025 94% figure for current inventory decisions.",
        ),
        "cold-room": note(
            "Cold room",
            "Long-term storage is 4 C and 15% relative humidity. The room is not a minus-18 freeze vault. Freeze vaults are not described here.",
        ),
        "distribution": note(
            "Distribution desk",
            "Research samples of NB-1882 ship on Tuesdays. Wheat samples ship on Thursdays. The desk does not quote a commercial packet price.",
        ),
        "field-book": note(
            "Regeneration field book",
            "NB-1882 regeneration plots are in Block A. NW-4401 plots are in Block C. Isolation distance for barley is 10 meters.",
        ),
        "prairie-gene": note(
            "Prairie Gene Trust (sister, not Nimbus)",
            "Prairie Gene Trust is a made-up maize bank. Its maize prefix is PM-. It does not hold NB-1882.",
        ),
        "contacts": note(
            "Nimbus contacts",
            "Distribution: 555-5501. Cold room alarm: 555-5500. Email: samples@nimbus-seed.example",
            "Curator names are omitted.",
        ),
        "phytosanitary": note(
            "Phytosanitary note",
            "Barley lots for export need a seed health test dated within 90 days. Wheat lots need 120 days. Fees are not listed.",
        ),
        "inventory": note(
            "Inventory snapshot (redacted)",
            "NB-1882: 12,400 seeds in cold room. NW-4401: 8,050 seeds. Weights in grams are omitted.",
        ),
        "omitted": note(
            "What this corpus does not contain",
            "Commercial packet prices, curator names, and GPS coordinates of the station are omitted on purpose.",
        ),
        "drying-room": note(
            "Drying room",
            "Seed drying is 15 C and 15% RH before the cold room. The drying room does not store maize from Prairie Gene Trust.",
        ),
        "labels": note(
            "Label color key",
            "Blue = barley (NB-). Yellow = wheat (NW-). Red is unused. Do not relabel NW-4401 as blue.",
        ),
        "hours": note(
            "Station public hours",
            "The public foyer is open 09:00-15:00 weekdays. The cold room is not on the public tour.",
        ),
    },
    "gold": [
        gold("ns-001", "Which crop is accession NB-1882?", True, ["barley", "six-row barley"], ["about", "nb-1882"], "NW-4401 is wheat."),
        gold("ns-002", "Which crop is accession NW-4401?", True, ["wheat", "hard red wheat"], ["nw-4401"], "Near-neighbour."),
        gold("ns-003", "What viability did the 2025 test report for NB-1882?", True, ["94%"], ["viability-2025"], "2022 was 81%."),
        gold("ns-004", "What viability did the 2022 test list for NB-1882?", True, ["81%"], ["viability-2022"], "Dated."),
        gold("ns-005", "What temperature is the Nimbus long-term cold room?", True, ["4 C", "4°C"], ["cold-room"], "Not a freeze vault."),
        gold("ns-006", "On which day do NB-1882 research samples ship?", True, ["Tuesdays", "Tuesday"], ["distribution"], "Wheat is Thursday."),
        gold("ns-007", "Which field block holds NB-1882 regeneration plots?", True, ["Block A"], ["field-book"], "Wheat is Block C."),
        gold("ns-008", "How many NB-1882 seeds are in the cold room according to the inventory snapshot?", True, ["12400", "12,400"], ["inventory"], "Not NW-4401."),
        gold("ns-009", "What label color is barley at Nimbus?", True, ["blue"], ["labels", "nb-1882"], "Wheat is yellow."),
        gold("ns-010", "What is the cold room alarm number?", True, ["555-5500"], ["contacts"], "Distribution is 555-5501."),
        gold("ns-011", "Does Prairie Gene Trust hold NB-1882?", True, ["no"], ["prairie-gene"], "Sister maize bank."),
        gold("ns-012", "What isolation distance is listed for barley regeneration?", True, ["10 meters", "10 m"], ["field-book"], "Literal."),
        gold("ns-013", "How much does a commercial packet of NB-1882 cost?", False, [], [], "No price."),
        gold("ns-014", "Who is the curator of Nimbus Seed Bank?", False, [], [], "Name omitted."),
        gold("ns-015", "What are the GPS coordinates of the station?", False, [], [], "Omitted."),
        gold("ns-016", "What is the phytosanitary test fee?", False, [], [], "No fee."),
    ],
}

LUMEN = {
    "id": "lumen-streetcar",
    "label": "Lumen Streetcar Authority",
    "industry": "Urban streetcar / transit",
    "group": "Transport",
    "prefix": "ls-",
    "fictional": True,
    "blurb": "A made-up streetcar in the city of Lumen. Line Amber vs Line Slate. 2021 Sunday headways disagree with 2026.",
    "examples": [
        "What is the weekday headway on Line Amber?",
        "According to the 2021 booklet, what was the Sunday headway on Line Amber?",
        "What is the 2026 adult fare on Lumen streetcars?",
    ],
    "docs": {
        "about": note(
            "Lumen Streetcar Authority — about (fictional transit)",
            "Lumen Streetcar Authority is a made-up agency in the invented city of Lumen. It is not a real metro.",
            "Line Amber runs the quay loop. Line Slate runs the ridge loop. They do not share track except at Exchange.",
        ),
        "line-amber": note(
            "Line Amber fact sheet",
            "Line Amber weekday headway is 12 minutes. Sunday headway is 20 minutes. Block 14 lays over at Quay.",
        ),
        "line-slate": note(
            "Line Slate fact sheet",
            "Line Slate weekday headway is 15 minutes. Sunday headway is 25 minutes. Block 14 does not work Slate.",
        ),
        "headway-2021": note(
            "Pocket booklet — 2021 (superseded Sunday times)",
            "The 2021 booklet listed Line Amber Sunday headway as 30 minutes. The current fact sheet is 20 minutes.",
        ),
        "exchange": note(
            "Exchange stop",
            "Exchange is the only place Amber and Slate platforms sit side by side. Transfer time posted: 3 minutes. No paid area.",
        ),
        "yard": note(
            "Carbarn",
            "Cars overnight at Quay Carbarn. Inspection pit P-2 is Amber-only. Slate cars use pit P-5.",
        ),
        "block-14": note(
            "Block 14 pad",
            "Block 14 lays over at Quay for 8 minutes on Line Amber. It is not a Slate block.",
        ),
        "ridge-bus": note(
            "Ridge Bus (sister, not the streetcar)",
            "Ridge Bus is a made-up diesel overlay. Its Sunday headway is 40 minutes. Ridge Bus is not Line Amber.",
        ),
        "hours": note(
            "Service span — current",
            "First Amber car: 05:40. Last Amber car: 23:10. Slate first car: 06:00. Last Slate: 22:40.",
        ),
        "contacts": note(
            "Lumen contacts",
            "Control: 555-6600. Lost and found: 555-6601. Email: control@lumen-streetcar.example",
            "General manager name omitted.",
        ),
        "accessibility": note(
            "Accessibility card",
            "All Amber stops are level boarding. Two Slate stops (Pine Cut and Old Quarry) remain flagged as high-floor until 2027.",
        ),
        "omitted": note(
            "What this corpus does not contain",
            "Fares, union wage tables, and ridership counts are omitted on purpose.",
        ),
        "signals": note(
            "Signal note",
            "Quay Junction is a stop signal for Amber only. Slate uses a separate dwarf signal labeled S-1.",
        ),
        "weather": note(
            "Leaf-fall bulletin",
            "In November, Amber adds 2 minutes to the Quay layover. Slate does not add time. The bulletin lists no sanding-truck schedule.",
        ),
        "maps-legend": note(
            "Map legend",
            "Amber is drawn ochre. Slate is drawn grey. Do not color Slate ochre on public boards.",
        ),
        "charter": note(
            "Charter desk",
            "Charters are accepted for Amber only, off-peak. The desk does not quote a charter price.",
        ),
    },
    "gold": [
        gold("ls-001", "What is the weekday headway on Line Amber?", True, ["12 minutes"], ["line-amber"], "Slate is 15."),
        gold("ls-002", "What is the Sunday headway on Line Amber according to the current fact sheet?", True, ["20 minutes"], ["line-amber"], "2021 was 30."),
        gold("ls-003", "According to the 2021 booklet, what was the Sunday headway on Line Amber?", True, ["30 minutes"], ["headway-2021"], "Dated."),
        gold("ls-004", "What is Line Slate's weekday headway?", True, ["15 minutes"], ["line-slate"], "Near-neighbour."),
        gold("ls-005", "Where does Block 14 lay over?", True, ["Quay"], ["line-amber", "block-14"], "Not Slate."),
        gold("ls-006", "What time is the first Amber car?", True, ["05:40"], ["hours"], "Slate is 06:00."),
        gold("ls-007", "Which Slate stops remain high-floor until 2027?", True, ["Pine Cut and Old Quarry", "Pine Cut", "Old Quarry"], ["accessibility"], "Amber is all level."),
        gold("ls-008", "What is the control phone number?", True, ["555-6600"], ["contacts"], "Not 555-6601."),
        gold("ls-009", "What is Ridge Bus Sunday headway?", True, ["40 minutes"], ["ridge-bus"], "Sister."),
        gold("ls-010", "Which inspection pit is Amber-only?", True, ["P-2"], ["yard"], "Slate is P-5."),
        gold("ls-011", "How much time does the November bulletin add to the Amber Quay layover?", True, ["2 minutes"], ["weather"], "Slate adds none."),
        gold("ls-012", "What posted transfer time is at Exchange?", True, ["3 minutes"], ["exchange"], "Literal."),
        gold("ls-013", "What is the 2026 adult fare on Lumen streetcars?", False, [], [], "Fares omitted."),
        gold("ls-014", "Who is the general manager of Lumen Streetcar Authority?", False, [], [], "Name omitted."),
        gold("ls-015", "How many riders did Amber carry last year?", False, [], [], "Ridership omitted."),
        gold("ls-016", "What does an Amber charter cost?", False, [], [], "No price."),
    ],
}

MARLOW = {
    "id": "marlow-clinic",
    "label": "Marlow Clinic Network",
    "industry": "Outpatient clinic",
    "group": "Health",
    "prefix": "mc-",
    "fictional": True,
    "blurb": "A made-up two-campus clinic. River has the retail pharmacy; Ridge has infusion. 2024 vs 2026 formulary disagree on theophylline.",
    "examples": [
        "What are weekday hours at the River Campus retail pharmacy?",
        "Does Ridge Campus have a retail pharmacy?",
        "What is the copay for an infusion at Ridge Campus?",
    ],
    "docs": {
        "about": note(
            "Marlow Clinic Network — about (fictional clinics)",
            "Marlow Clinic Network is a made-up outpatient network with two campuses: River and Ridge. It is not a real hospital system.",
            "River Campus has the retail pharmacy. Ridge Campus has the infusion suite. Neither campus is an emergency department.",
        ),
        "river-campus": note(
            "River Campus",
            "River Campus houses primary care and the retail pharmacy. It does not house infusion chairs. Address: 8 River Walk (invented).",
        ),
        "ridge-campus": note(
            "Ridge Campus",
            "Ridge Campus houses the infusion suite. Hours 07:00-15:30 weekdays. There is no retail pharmacy at Ridge.",
        ),
        "pharmacy-hours": note(
            "River retail pharmacy hours",
            "Monday-Friday 08:00-18:00. Saturday 09:00-13:00. Sunday closed. Ridge has no retail pharmacy window.",
        ),
        "formulary-2026": note(
            "Outpatient formulary — 2026",
            "The 2026 formulary dropped theophylline. Albuterol inhalers remain listed. This list supersedes the 2024 card.",
        ),
        "formulary-2024": note(
            "Outpatient formulary — 2024 (superseded)",
            "The 2024 card still listed theophylline tablets. Do not treat theophylline as current stock.",
        ),
        "infusion": note(
            "Infusion suite",
            "Infusion is Ridge-only, 07:00-15:30 weekdays. Pre-meds are stored in Fridge R-2. River Campus does not infuse.",
        ),
        "lab": note(
            "Clinic lab",
            "Blood draw at River: 07:00-11:00. Ridge draws only for infusion patients, 06:30-08:00. No public walk-in at Ridge.",
        ),
        "cedar-urgent": note(
            "Cedar Urgent (sister, not Marlow)",
            "Cedar Urgent is a made-up stand-alone urgent care. It is open 10:00-22:00 including Sunday. It is not River Campus.",
        ),
        "contacts": note(
            "Marlow contacts",
            "River desk: 555-7701. Ridge infusion: 555-7702. Email: desks@marlow-clinic.example",
            "Chief of medicine name omitted.",
        ),
        "records": note(
            "Records window",
            "Release-of-records at River only, Tuesday and Thursday 10:00-14:00. Ridge does not release charts over the counter.",
        ),
        "omitted": note(
            "What this corpus does not contain",
            "Copays, insurance contracts, and clinician names are omitted on purpose.",
        ),
        "parking": note(
            "Parking note",
            "River visitor lots close at 19:00. Ridge infusion parking is Lot G, open 06:00-16:00. Overnight parking is not offered.",
        ),
        "pharmacy-stock": note(
            "Pharmacy stock note",
            "Albuterol is stocked at River. Theophylline is not stocked in 2026. Ridge infusion does not dispense retail inhalers.",
        ),
        "hours-holiday": note(
            "Holiday card 2026",
            "Both campuses closed 25 December 2026. Infusion is not rescheduled on that date. The card does not list a new-year Saturday clinic.",
        ),
        "referrals": note(
            "Referral desk",
            "Outside referrals for infusion must name Ridge Campus. Referrals that name River for infusion are returned.",
        ),
    },
    "gold": [
        gold("mc-001", "What are weekday hours at the River Campus retail pharmacy?", True, ["08:00-18:00"], ["pharmacy-hours"], "Ridge has no pharmacy."),
        gold("mc-002", "Does Ridge Campus have a retail pharmacy?", True, ["no"], ["ridge-campus", "pharmacy-hours"], "Near-neighbour."),
        gold("mc-003", "What are Ridge infusion hours on weekdays?", True, ["07:00-15:30"], ["ridge-campus", "infusion"], "Not River."),
        gold("mc-004", "Is theophylline on the 2026 outpatient formulary?", True, ["no", "dropped theophylline"], ["formulary-2026"], "2024 still listed it."),
        gold("mc-005", "Did the 2024 formulary list theophylline tablets?", True, ["yes"], ["formulary-2024"], "Dated."),
        gold("mc-006", "What are Cedar Urgent hours?", True, ["10:00-22:00"], ["cedar-urgent"], "Sister."),
        gold("mc-007", "When is the records window open at River?", True, ["Tuesday and Thursday 10:00-14:00"], ["records"], "Ridge does not release."),
        gold("mc-008", "What is the Ridge infusion phone number?", True, ["555-7702"], ["contacts"], "River is 555-7701."),
        gold("mc-009", "Which fridge stores infusion pre-meds?", True, ["Fridge R-2", "R-2"], ["infusion"], "Literal."),
        gold("mc-010", "Are both campuses closed on 25 December 2026?", True, ["yes"], ["hours-holiday"], "Literal."),
        gold("mc-011", "Where is River Campus?", True, ["8 River Walk"], ["river-campus"], "Address."),
        gold("mc-012", "Which lot is Ridge infusion parking?", True, ["Lot G"], ["parking"], "Not River lots."),
        gold("mc-013", "What is the copay for an infusion at Ridge Campus?", False, [], [], "Copays omitted."),
        gold("mc-014", "Who is the chief of medicine at Marlow?", False, [], [], "Name omitted."),
        gold("mc-015", "Is there a Saturday clinic on New Year's Day?", False, [], [], "Holiday card silent."),
        gold("mc-016", "Which insurers does Marlow accept?", False, [], [], "Contracts omitted."),
    ],
}

SALTWIND = {
    "id": "saltwind-coop",
    "label": "Saltwind Fisheries Co-op",
    "industry": "Commercial fishing cooperative",
    "group": "Agriculture",
    "prefix": "sw-",
    "fictional": True,
    "blurb": "A made-up fishing co-op. Vessel Storm Petrel vs Kelp Wren. 2024 vs current Dungeness opener dates disagree.",
    "examples": [
        "On what date does the current Dungeness opener start at Saltwind?",
        "Which Saltwind vessel is named Storm Petrel?",
        "What is the ex-vessel price for Dungeness at Saltwind?",
    ],
    "docs": {
        "about": note(
            "Saltwind Fisheries Co-op — about (fictional co-op)",
            "Saltwind is a made-up fishing cooperative on an invented coast. It is not a real association.",
            "Member vessels include Storm Petrel (crab) and Kelp Wren (troll salmon). Ice plant sits on Pier 2.",
        ),
        "storm-petrel": note(
            "Vessel Storm Petrel",
            "Storm Petrel is a crabber. Hold capacity 40 pots on deck. It does not troll salmon. Radio call: Saltwind-Petrel.",
        ),
        "kelp-wren": note(
            "Vessel Kelp Wren",
            "Kelp Wren is a salmon troller. It does not carry crab pots. Radio call: Saltwind-Wren.",
        ),
        "opener-current": note(
            "Season card — current",
            "Dungeness opener: 1 December. Salmon troll opener: 1 May. These are the current Saltwind card dates.",
        ),
        "opener-2024": note(
            "Season card — 2024 (superseded Dungeness date)",
            "The 2024 card listed a Dungeness opener of 15 November. The current card is 1 December.",
        ),
        "ice-plant": note(
            "Ice plant hours",
            "Ice plant: 04:00-14:00 daily during season. After 14:00, ice is locked. The plant does not quote a price per ton.",
        ),
        "pier-2": note(
            "Pier 2",
            "Offloads for Storm Petrel use Pier 2 hoist H-4. Kelp Wren uses Pier 1 davit. Fuel is not sold at Pier 2.",
        ),
        "gull-packers": note(
            "Gull Packers (sister, not the co-op)",
            "Gull Packers is a made-up private buyer on Pier 5. Its ice window is 06:00-12:00. Gull is not Saltwind.",
        ),
        "radio": note(
            "Radio card",
            "Co-op channel: Saltwind-1. Storm Petrel hail: Saltwind-Petrel. Kelp Wren hail: Saltwind-Wren.",
        ),
        "contacts": note(
            "Saltwind contacts",
            "Ice plant: 555-8800. Office: 555-8801. Email: ice@saltwind-coop.example",
            "President's name omitted.",
        ),
        "safety": note(
            "Deck safety card",
            "PFDs on Pier 2 during pot lifts. Kelp Wren troll crews use harnesses at the stern. No injury counts listed.",
        ),
        "omitted": note(
            "What this corpus does not contain",
            "Ex-vessel prices, quota pounds, and officer names are omitted on purpose.",
        ),
        "scale-house": note(
            "Scale house",
            "Crab is weighed at Scale A on Pier 2. Salmon is weighed at Scale B on Pier 1. Tickets do not print a dollar amount.",
        ),
        "weather-limit": note(
            "Small-craft note",
            "Storm Petrel does not leave in small-craft advisory. Kelp Wren follows the same rule. No wave-height number is printed.",
        ),
        "gear": note(
            "Gear loft",
            "Crab pots stored in Loft C. Troll gurdies stored in Loft A. Do not store pots in Loft A.",
        ),
        "meetings": note(
            "Member meeting notice",
            "Monthly meeting: first Tuesday, 19:00, ice-plant break room. The notice does not list a stipend.",
        ),
    },
    "gold": [
        gold("sw-001", "On what date does the current Dungeness opener start at Saltwind?", True, ["1 December", "December 1"], ["opener-current"], "2024 was 15 November."),
        gold("sw-002", "According to the 2024 season card, when did Dungeness open?", True, ["15 November", "November 15"], ["opener-2024"], "Dated."),
        gold("sw-003", "What is the salmon troll opener date on the current card?", True, ["1 May", "May 1"], ["opener-current"], "Not crab."),
        gold("sw-004", "Is Storm Petrel a crabber or a troller?", True, ["crabber"], ["storm-petrel", "about"], "Kelp Wren is troll."),
        gold("sw-005", "What are ice plant hours during season?", True, ["04:00-14:00"], ["ice-plant"], "Gull is 06:00-12:00."),
        gold("sw-006", "Which hoist do Storm Petrel offloads use?", True, ["H-4"], ["pier-2"], "Kelp Wren is Pier 1."),
        gold("sw-007", "What is the ice plant phone number?", True, ["555-8800"], ["contacts"], "Office is 555-8801."),
        gold("sw-008", "Where is crab weighed?", True, ["Scale A on Pier 2", "Scale A"], ["scale-house"], "Salmon is Scale B."),
        gold("sw-009", "What is Gull Packers ice window?", True, ["06:00-12:00"], ["gull-packers"], "Sister."),
        gold("sw-010", "Where are crab pots stored?", True, ["Loft C"], ["gear"], "Gurdies in Loft A."),
        gold("sw-011", "When is the monthly member meeting?", True, ["first Tuesday, 19:00"], ["meetings"], "Literal."),
        gold("sw-012", "What radio hail does Kelp Wren use?", True, ["Saltwind-Wren"], ["kelp-wren", "radio"], "Petrel is Saltwind-Petrel."),
        gold("sw-013", "What is the ex-vessel price for Dungeness at Saltwind?", False, [], [], "Prices omitted."),
        gold("sw-014", "Who is the president of Saltwind Fisheries Co-op?", False, [], [], "Name omitted."),
        gold("sw-015", "How many quota pounds does Storm Petrel hold?", False, [], [], "Quota omitted."),
        gold("sw-016", "What wave height grounds Storm Petrel?", False, [], [], "No number printed."),
    ],
}

WORLDS = (ORION, PORTHAVEN, NIMBUS, LUMEN, MARLOW, SALTWIND)
