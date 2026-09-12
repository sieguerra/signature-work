#!/usr/bin/env python3
"""Emit fictional industry corpora. Run from the repo root. Idempotent overwrites."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def note(*paragraphs: str) -> str:
    return "\n\n".join(p.strip() for p in paragraphs) + "\n"


def gold(qid: str, question: str, answerable: bool, answers: list[str], docs: list[str], notes: str) -> dict:
    return {
        "question_id": qid,
        "question": question,
        "answerable": answerable,
        "answers": answers,
        "supporting_doc_ids": docs,
        "notes": notes,
    }


def write_world(world: dict) -> None:
    corpus_dir = ROOT / "datasets" / world["id"] / "corpus"
    gold_dir = ROOT / "datasets" / world["id"] / "gold"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)
    for name, text in world["docs"].items():
        (corpus_dir / f"{name}.txt").write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    stale = {path.stem for path in corpus_dir.glob("*.txt")} - set(world["docs"])
    for stem in stale:
        (corpus_dir / f"{stem}.txt").unlink()
    lines = [
        f"# Gold over datasets/{world['id']}/corpus/. Fictional world; verify every row against the .txt files.",
        f"# Prefix {world['prefix']}. Harbor and DKU gold files are unchanged.",
        "",
    ]
    for row in world["gold"]:
        lines.append(json.dumps(row, ensure_ascii=False))
    (gold_dir / "questions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "datasets" / world["id"] / "README.md").write_text(
        f"# {world['label']}\n\n"
        f"**Industry:** {world['industry']}\n\n"
        f"{world['blurb']}\n\n"
        f"Fictional on purpose (ADR 003 / ADR 010). Not a real company. "
        f"{len(world['docs'])} notes, {len(world['gold'])} gold questions.\n",
        encoding="utf-8",
    )


NORTHHAVEN = {
    "id": "northhaven-water",
    "label": "Northhaven Water District",
    "industry": "Municipal water utility",
    "group": "Utilities",
    "prefix": "nw-",
    "fictional": True,
    "blurb": "A made-up coastal utility in Cedar County. Plover Plant treats river water; Brine Wellfield pumps groundwater. Dated fluoride and Saturday desk hours disagree on purpose.",
    "examples": [
        "What are Saturday walk-in hours at the Cedar Street billing desk according to the current notice?",
        "What fluoride residual does the March 2026 water quality sheet list?",
        "Who is the general manager of Northhaven Water District?",
    ],
    "docs": {
        "about": note(
            "Northhaven Water District — about (fictional utility)",
            "Northhaven Water District is a made-up municipal utility serving the invented town of Northhaven in Cedar County. It is not a real agency.",
            "The district operates two sources: Plover Plant on the Cedar River (surface water) and Brine Wellfield (groundwater). The Cedar Street billing office is at 14 Cedar Street.",
            "The district does not serve Redcliff, which has its own alliance.",
        ),
        "plover-plant": note(
            "Plover Plant operations",
            "Plover Plant treats Cedar River water with coagulation, filtration, and chlorine. Design capacity is 8 million gallons per day. The plant's labeled finished-water pump is P-12.",
            "Plover Plant does not house the Brine well pumps. Those sit at Brine Wellfield, four miles inland.",
        ),
        "brine-wellfield": note(
            "Brine Wellfield operations",
            "Brine Wellfield has twelve wells. Well 7 is the duty well on weekdays. Well 12 is standby only and is not used unless Well 7 is offline.",
            "Wellfield water is groundwater. It is not Cedar River water and does not pass through Plover Plant filters.",
        ),
        "billing-desk-current": note(
            "Cedar Street billing desk — current notice (posted March 2026)",
            "Walk-in hours at the Cedar Street billing desk: Monday-Friday 08:30-17:00. Saturday 09:00-13:00. Sunday closed.",
            "After-hours payments go in the drop box. This notice supersedes the 2023 Saturday window.",
        ),
        "billing-desk-2023": note(
            "Cedar Street billing desk — 2023 notice (superseded)",
            "This 2023 notice is kept for contrast. Saturday walk-in hours were 10:00-12:00. Monday-Friday were 09:00-16:00.",
            "The March 2026 notice is the current desk schedule. Do not treat this 2023 card as current.",
        ),
        "water-quality-2026": note(
            "Finished water quality sheet — March 2026",
            "Fluoride residual at the entry point: 0.7 mg/L. Free chlorine residual: 0.9 mg/L. pH: 7.4.",
            "These are March 2026 entry-point numbers for water leaving Plover Plant. They are not the 2021 report numbers.",
        ),
        "water-quality-2021": note(
            "Finished water quality report — 2021 (superseded numbers)",
            "The 2021 annual report listed fluoride residual 1.2 mg/L and free chlorine 1.1 mg/L.",
            "Those 2021 numbers are not the March 2026 residuals. Keep this file only as a dated distractor.",
        ),
        "boil-advisories": note(
            "Boil water advisories — status board",
            "Zone 4 boil water advisory was lifted on 12 March 2026. Zone 9 remains under a boil water advisory as of 12 March 2026.",
            "The board does not list a lift date for Zone 9. It does not mention Redcliff.",
        ),
        "contacts": note(
            "Northhaven Water contacts",
            "24-hour operations line: 555-0140. Billing desk (business hours): 555-0141. Email: billing@northhaven-water.example",
            "No staff names are listed here. The general manager's name is omitted on purpose.",
        ),
        "emergency-plan": note(
            "Emergency notification plan",
            "Priority 1 alerts use the 24-hour operations line 555-0140. Priority 2 door hangers go to Zone 9 first when a boil advisory is active.",
            "The plan does not include a public rate schedule.",
        ),
        "redcliff-alliance": note(
            "Redcliff Water Alliance (sister utility, not Northhaven)",
            "Redcliff Water Alliance serves the invented town of Redcliff, west of Cedar County. Its Saturday counter hours are 08:00-11:00.",
            "Redcliff is not Northhaven Water District. Do not use Redcliff hours as Northhaven hours.",
        ),
        "meter-shop": note(
            "Meter shop",
            "The meter shop is behind the Cedar Street office. Residential meters are swapped on Tuesdays. The shop does not quote a price per gallon.",
            "Commercial compound meters are stored on Rack C, not at Plover Plant.",
        ),
        "fleet": note(
            "Utility fleet list",
            "Valve truck V-2 and leak van L-6 are assigned to Plover Plant. Wellfield truck W-9 stays at Brine Wellfield overnight.",
            "There is no aviation fuel truck. That belongs to other worlds.",
        ),
        "cross-connection": note(
            "Cross-connection control pamphlet",
            "Backflow tests for cafes on Harbor Walk are due each May. The pamphlet does not list a test fee.",
            "Residential hose bib vacuum breakers are required. The pamphlet does not name a contractor.",
        ),
        "lab-hours": note(
            "District lab hours",
            "The process lab at Plover Plant accepts process samples 06:00-14:00 Monday-Friday. It does not accept public well samples from Brine residents on Saturday.",
            "Weekend bacteriological bottles go to the county lab, which is not described here.",
        ),
        "omitted-rates": note(
            "What this corpus does not contain",
            "Residential volumetric rates, connection fees, and the general manager's name are omitted on purpose so those questions are unanswerable from local evidence.",
            "Do not invent a dollar per gallon figure.",
        ),
    },
    "gold": [
        gold("nw-001", "What are Saturday walk-in hours at the Cedar Street billing desk according to the current notice?", True, ["09:00-13:00", "9:00-13:00"], ["billing-desk-current"], "2023 notice is 10:00-12:00."),
        gold("nw-002", "According to the 2023 Cedar Street billing notice, what were Saturday walk-in hours?", True, ["10:00-12:00"], ["billing-desk-2023"], "Dated contrast with nw-001."),
        gold("nw-003", "What fluoride residual does the March 2026 water quality sheet list?", True, ["0.7 mg/L", "0.7"], ["water-quality-2026"], "2021 report is 1.2 mg/L."),
        gold("nw-004", "What fluoride residual did the 2021 water quality report list?", True, ["1.2 mg/L", "1.2"], ["water-quality-2021"], "Dated contrast."),
        gold("nw-005", "On what date was the Zone 4 boil water advisory lifted?", True, ["12 March 2026", "March 12, 2026"], ["boil-advisories"], "Zone 9 was not lifted."),
        gold("nw-006", "What is the 24-hour operations line for Northhaven Water District?", True, ["555-0140"], ["contacts", "emergency-plan"], "Not the billing number 555-0141."),
        gold("nw-007", "What is the design capacity of Plover Plant?", True, ["8 million gallons per day", "8 million gallons"], ["plover-plant"], "Not wellfield capacity."),
        gold("nw-008", "Which well is the weekday duty well at Brine Wellfield?", True, ["Well 7"], ["brine-wellfield"], "Well 12 is standby."),
        gold("nw-009", "Where is the Cedar Street billing office?", True, ["14 Cedar Street"], ["about"], "Literal address."),
        gold("nw-010", "What are Saturday counter hours at Redcliff Water Alliance?", True, ["08:00-11:00", "8:00-11:00"], ["redcliff-alliance"], "Sister-utility distractor."),
        gold("nw-011", "Is Zone 9 still under a boil water advisory as of 12 March 2026?", True, ["yes", "remains under a boil water advisory"], ["boil-advisories"], "Contrast with Zone 4."),
        gold("nw-012", "Which truck stays at Brine Wellfield overnight?", True, ["W-9", "wellfield truck W-9"], ["fleet"], "Not V-2."),
        gold("nw-013", "Who is the general manager of Northhaven Water District?", False, [], [], "Name omitted."),
        gold("nw-014", "What is the residential price per gallon of water in Northhaven?", False, [], [], "Rates omitted."),
        gold("nw-015", "When will the Zone 9 boil advisory be lifted?", False, [], [], "No lift date listed."),
        gold("nw-016", "What fee does the district charge for a backflow test?", False, [], [], "Pamphlet has no fee."),
    ],
}

KESTREL = {
    "id": "kestrel-aero",
    "label": "Kestrel Aero Components",
    "industry": "Aerospace machining",
    "group": "Manufacturing",
    "prefix": "ka-",
    "fictional": True,
    "blurb": "A made-up machine shop in Red Mesa. Hangar 2 cuts titanium; Shop 6 cuts aluminum. 2018 vs 2025 spec letters disagree.",
    "examples": [
        "Which building at Kestrel Aero machines titanium bulkheads?",
        "What AMS specification letter does the 2025 traveler require for titanium plate?",
        "What is the unit price of a Kestrel bulkhead?",
    ],
    "docs": {
        "about": note(
            "Kestrel Aero Components — about (fictional shop)",
            "Kestrel Aero Components is a made-up job shop in the invented town of Red Mesa. It is not a real aerospace supplier.",
            "Hangar 2 machines titanium. Shop 6 machines aluminum. The traveler office is in Hangar 2, bay C.",
        ),
        "hangar-2": note(
            "Hangar 2 titanium cell",
            "Hangar 2 cuts titanium bulkheads on mill M-40. Active lot for the current order is KX-441. Coolant is the titanium-only tank, not the aluminum tank from Shop 6.",
            "Food is banned on the Hangar 2 floor.",
        ),
        "shop-6": note(
            "Shop 6 aluminum cell",
            "Shop 6 cuts aluminum fittings on mill M-11. Active lot is AL-902. Shop 6 does not cut titanium and does not store lot KX-441.",
        ),
        "traveler-2025": note(
            "Titanium traveler — 2025 issue",
            "Titanium plate must be AMS 4911R. The 2025 traveler rejects AMS 4911N. Heat-treat condition: annealed.",
            "This 2025 issue is the current traveler for Hangar 2 titanium jobs.",
        ),
        "traveler-2018": note(
            "Titanium traveler — 2018 issue (obsolete)",
            "The 2018 traveler called for AMS 4911N. That letter is obsolete. Keep this sheet only as a dated distractor.",
            "Do not use AMS 4911N on current Hangar 2 jobs.",
        ),
        "shifts": note(
            "Shift board",
            "Shift A: 06:00-14:30. Shift B: 14:30-23:00. There is no third shift. The tool crib is staffed on Shift A only.",
        ),
        "quality": note(
            "Quality registration",
            "Kestrel is registered to AS9100D. It is not registered to ISO 13485. The quality office is the glass room in Hangar 2.",
        ),
        "calibration": note(
            "Calibration calendar",
            "Micrometer set T-7 is due 1 November 2026. CMM C-2 is due 15 January 2027. The calendar does not list a calibration vendor price.",
        ),
        "fay-aerospace": note(
            "Fay Aerospace (sister shop, not Kestrel)",
            "Fay Aerospace is a made-up composites shop across the highway. Its only mill is a 3-axis router. Fay does not hold lot KX-441.",
            "Do not treat Fay hours or specs as Kestrel's.",
        ),
        "shipping": note(
            "Shipping dock",
            "Finished titanium parts leave Dock West. Aluminum leaves Dock East. The dock does not accept customer pickup after 16:00.",
        ),
        "ncr-log": note(
            "Open nonconformance log (redacted)",
            "NCR-88 is an open scratch on lot AL-902 in Shop 6. No open NCR is listed for lot KX-441.",
            "Costs and customer names are omitted.",
        ),
        "ppe": note(
            "PPE card",
            "Hangar 2 requires a face shield at the pickle tank. Shop 6 requires safety glasses only. The card does not mention a uniform vendor.",
        ),
        "tool-crib": note(
            "Tool crib",
            "The crib issues 1/2-inch titanium end mills only on Shift A. After 14:30, mills are locked. Aluminum end mills live in Shop 6, drawer 4.",
        ),
        "contacts": note(
            "Kestrel contacts",
            "Traveler desk: 555-2201. Quality office: 555-2202. Email: travelers@kestrel-aero.example",
            "Officer names are omitted on purpose.",
        ),
        "omitted": note(
            "What this corpus does not contain",
            "Unit prices, the owner's name, and ITAR exemption numbers are omitted so those questions are unanswerable from local evidence.",
        ),
        "break-room": note(
            "Break room note",
            "The Hangar 2 break room microwave is off-limits to Shop 6 crews during Shift A. Coffee urn hours are 05:45-09:00.",
        ),
    },
    "gold": [
        gold("ka-001", "Which building at Kestrel Aero machines titanium bulkheads?", True, ["Hangar 2"], ["about", "hangar-2"], "Shop 6 is aluminum."),
        gold("ka-002", "What is the active titanium lot on mill M-40?", True, ["KX-441"], ["hangar-2"], "AL-902 is aluminum."),
        gold("ka-003", "What AMS specification letter does the 2025 traveler require for titanium plate?", True, ["AMS 4911R", "4911R"], ["traveler-2025"], "2018 was 4911N."),
        gold("ka-004", "What AMS specification did the 2018 titanium traveler call for?", True, ["AMS 4911N", "4911N"], ["traveler-2018"], "Dated contrast."),
        gold("ka-005", "What are Shift A hours at Kestrel Aero?", True, ["06:00-14:30"], ["shifts"], "Not Shift B."),
        gold("ka-006", "Which quality standard is Kestrel registered to?", True, ["AS9100D"], ["quality"], "Not ISO 13485."),
        gold("ka-007", "When is micrometer set T-7 due for calibration?", True, ["1 November 2026", "November 1, 2026"], ["calibration"], "Not CMM C-2."),
        gold("ka-008", "Which dock do finished titanium parts leave from?", True, ["Dock West"], ["shipping"], "Aluminum is Dock East."),
        gold("ka-009", "Which lot is named on open NCR-88?", True, ["AL-902"], ["ncr-log"], "Not KX-441."),
        gold("ka-010", "What is the traveler desk phone number?", True, ["555-2201"], ["contacts"], "Not quality 555-2202."),
        gold("ka-011", "Does Shop 6 cut titanium?", True, ["no", "does not cut titanium"], ["shop-6"], "Near-neighbour."),
        gold("ka-012", "Where do aluminum end mills live?", True, ["Shop 6, drawer 4", "drawer 4"], ["tool-crib"], "Not Hangar 2."),
        gold("ka-013", "What is the unit price of a Kestrel bulkhead?", False, [], [], "Prices omitted."),
        gold("ka-014", "Who owns Kestrel Aero Components?", False, [], [], "Names omitted."),
        gold("ka-015", "What ITAR exemption number does Kestrel hold?", False, [], [], "Omitted."),
        gold("ka-016", "What does Fay Aerospace charge per hour?", False, [], [], "Sister shop, no rates."),
    ],
}


def _rest_worlds() -> tuple:
    import importlib.util

    path = Path(__file__).with_name("industry_worlds_rest.py")
    spec = importlib.util.spec_from_file_location("industry_worlds_rest", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.WORLDS


HARBOR_META = {
    "id": "harbor",
    "label": "Harbor Institute",
    "industry": "Fictional research campus",
    "group": "Campus",
    "corpus_dir": "datasets/corpus",
    "gold_path": "datasets/gold/questions.jsonl",
    "fictional": True,
    "examples": [
        "When is the Harbor Institute Library open on Saturday?",
        "What is the late-return fine at the Harbor Institute Library?",
        "How much does a meal cost at Tide Canteen?",
    ],
}

DKU_META = {
    "id": "dku",
    "label": "Duke Kunshan University",
    "industry": "University campus (public facts)",
    "group": "Campus",
    "corpus_dir": "datasets/dku/corpus",
    "gold_path": "datasets/dku/gold/questions.jsonl",
    "fictional": False,
    "examples": [
        "According to the current DKU Library Locations and Hours page, what are the 1st floor information desk hours on Saturday?",
        "What are breakfast hours at University Dining in the Academic Building?",
        "What time does breakfast end at Halal Dining at the Conference Center?",
    ],
}


def registry_row(world: dict) -> dict:
    return {
        "id": world["id"],
        "label": world["label"],
        "industry": world["industry"],
        "group": world["group"],
        "corpus_dir": f"datasets/{world['id']}/corpus",
        "gold_path": f"datasets/{world['id']}/gold/questions.jsonl",
        "fictional": world.get("fictional", True),
        "examples": world["examples"],
    }


def main() -> int:
    worlds = (NORTHHAVEN, KESTREL) + _rest_worlds()
    for world in worlds:
        write_world(world)
        print(f"wrote {world['id']}: {len(world['docs'])} docs, {len(world['gold'])} gold")
    registry = {
        "default": "dku",
        "corpora": [HARBOR_META, DKU_META] + [registry_row(world) for world in worlds],
    }
    path = ROOT / "datasets" / "registry.json"
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(registry['corpora'])} corpora)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
