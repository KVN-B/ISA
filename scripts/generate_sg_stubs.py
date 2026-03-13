"""
Generate stub text files for S&G items that don't yet have PDFs.

For each of the 36 unwritten Standards & Guidelines, creates a structured
text file in data/full_texts/sg-stub-{n}.txt containing all known metadata:
title, status, phase, related draft regulations, subject area, and notes.

This gives the chatbot meaningful context about each S&G even before the
actual document is written.

Usage:
    cd /path/to/ISA\ App
    python3 scripts/generate_sg_stubs.py
"""

import json
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
TEXT_DIR = DATA_DIR / "full_texts"
TEXT_DIR.mkdir(exist_ok=True)

STATUS_LABELS = {
    "to_be_developed":          "To be developed — no work has started yet",
    "under_development":        "Under development — LTC is currently drafting this S&G",
    "tor_prepared":             "Terms of Reference prepared — scope defined, drafting not yet started",
    "in_suspense_document":     "In suspense — linked to provisions deferred from the main regulatory text",
    "to_be_merged":             "To be merged with another S&G item",
    "prepared":                 "Prepared — adopted by the Council at ISBA/27",
}

PHASE_LABELS = {
    1: "Phase 1 — must be ready before adoption of the Exploitation Regulations",
    2: "Phase 2 — must be ready before the first application for exploitation is approved",
    3: "Phase 3 — must be ready before commercial mining commences",
}

TYPE_LABELS = {
    "standard_and_guideline": "Standard AND Guideline — contains both binding and recommendatory elements",
    "standard":               "Standard — legally BINDING on contractors and the ISA",
    "guideline":              "Guideline — recommendatory in nature, not legally binding",
}


def generate_stub(item: dict, all_items: list[dict]) -> str:
    n           = item.get("number", "?")
    title       = item.get("title") or item.get("short_title", "—")
    short_title = item.get("short_title") or title
    status      = item.get("status", "unknown")
    phase       = item.get("phase")
    phase_note  = item.get("phase_note", "")
    item_type   = item.get("type", "")
    subject     = item.get("subject_area", "")
    regs        = item.get("draft_regulations") or []
    annexes     = item.get("annexes") or []
    isba_doc    = item.get("isba_document") or ""

    lines = [
        f"STANDARDS AND GUIDELINES ITEM #{n}",
        f"{'=' * 60}",
        f"Title:          {title}",
        f"Short title:    {short_title}",
        f"ISA document:   {isba_doc or '(not yet assigned)'}",
        f"",
        f"STATUS: {STATUS_LABELS.get(status, status)}",
        f"",
    ]

    # Phase
    if phase:
        lines.append(f"DEVELOPMENT PHASE: {PHASE_LABELS.get(phase, f'Phase {phase}')}")
    else:
        lines.append("DEVELOPMENT PHASE: Phase not yet determined / TBD")
    if phase_note:
        lines.append(f"  Note: {phase_note}")
    lines.append("")

    # Type
    if item_type:
        lines.append(f"LEGAL NATURE: {TYPE_LABELS.get(item_type, item_type)}")
        lines.append("")

    # Subject area
    if subject:
        lines.append(f"SUBJECT AREA: {subject}")
        lines.append("")

    # Related draft regulations
    if regs:
        lines.append(f"RELATED DRAFT REGULATIONS ({len(regs)}):")
        for r in regs:
            lines.append(f"  • {r}")
        lines.append("")

    # Annexes
    if annexes:
        lines.append(f"RELATED ANNEXES: {', '.join(annexes)}")
        lines.append("")

    # Special notes by status
    if status == "in_suspense_document":
        lines += [
            "IMPORTANT: This S&G is linked to provisions that are currently in the",
            "SUSPENSE DOCUMENT (ISBA/31/C/CRP.3). These provisions have been deferred",
            "from the main regulatory text pending further negotiation. The S&G cannot",
            "be finalised until the parent regulatory provision is resolved.",
            "",
        ]
    elif status == "to_be_merged":
        lines += [
            "NOTE: This S&G item is expected to be merged with a related item.",
            "The merged document will cover the combined scope of both items.",
            "",
        ]
    elif status == "tor_prepared":
        lines += [
            "NOTE: Terms of Reference (ToR) have been prepared for this S&G,",
            "defining its scope and objectives. Drafting has not yet commenced.",
            "",
        ]
    elif status == "under_development":
        lines += [
            "NOTE: This S&G is actively being drafted by the Legal and Technical",
            "Commission (LTC). A consultation draft may be published before adoption.",
            "",
        ]

    # Context from related regulations (placeholder for future linking)
    lines += [
        f"WHAT THIS S&G WILL COVER:",
        f"When adopted, this {'Standard and Guideline' if item_type == 'standard_and_guideline' else item_type.replace('_',' ').title() or 'S&G'} will provide detailed",
        f"requirements and/or guidance on: {short_title.lower()}.",
    ]
    if regs:
        lines.append(f"It gives operational effect to {', '.join(regs[:3])}" +
                     (f" and {len(regs)-3} other regulations." if len(regs) > 3 else "."))
    lines += [
        "",
        f"{'=' * 60}",
        f"Source: ISA standards_guidelines.json · Item #{n} · Status: {status}",
        f"This is a METADATA STUB — no full text exists yet for this S&G.",
        f"It is one of 36 S&G items yet to be drafted as of March 2026.",
    ]

    return "\n".join(lines)


def main():
    sg_path = DATA_DIR / "standards_guidelines.json"
    if not sg_path.exists():
        print("ERROR: data/standards_guidelines.json not found.")
        return

    sg_data = json.loads(sg_path.read_text(encoding="utf-8"))
    items   = sg_data.get("standards_and_guidelines", [])
    no_pdf  = [s for s in items if not s.get("url_pdf")]

    print(f"Generating stubs for {len(no_pdf)} unwritten S&G items...\n")
    ok = 0
    for item in no_pdf:
        n       = item.get("number", "?")
        stub_id = f"sg-stub-{n}"
        dest    = TEXT_DIR / f"{stub_id}.txt"

        content = generate_stub(item, items)
        dest.write_text(content, encoding="utf-8")
        print(f"  #{n:2} {item.get('short_title','')[:45]} → {stub_id}.txt")
        ok += 1

    print(f"\nDone. {ok} stubs written to data/full_texts/")


if __name__ == "__main__":
    main()
