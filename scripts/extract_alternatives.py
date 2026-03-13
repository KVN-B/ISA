"""
Extract bracketed alternatives from ISA CRP.2/Rev.2 regulatory text.

Captures five types:
  1. [Alt.1 text] [Alt.2 text]  — explicit competing alternatives
  2. [A] / [B]                  — slash formulation choices
  3. [N. Alt. text]             — alternative paragraphs (labelled .Alt.)
  4. Regulation N Alt.          — full regulation alternates
  5. [N. text]                  — optional/new standalone paragraphs (include vs delete)

Each alternative includes the FULL TEXT of its parent regulation so
the voting page can show complete context.

Usage:
    cd /path/to/ISA\ App
    python3 scripts/extract_alternatives.py
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
TEXT_DIR = DATA_DIR / "full_texts"

SOURCE_ID  = "further-rev-consolidated-text-clean-isba31c-crp2-rev2-2026-02"
SOURCE_REF = "ISBA/31/C/CRP.2/Rev.2"


# ── Bracket-aware extraction ──────────────────────────────────────────────────

def find_matching_bracket(text: str, start: int) -> int:
    """Given text[start] == '[', return index of the matching ']'. -1 if not found."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return i
    return -1


# ── Regulation index & full-body extraction ───────────────────────────────────

# Matches regulation headers like "Regulation 48", "Regulation 48 bis", "Regulation 25 Alt."
REG_HEADER_RE = re.compile(
    r"^(Regulation\s+\d+[\w\s\.]*?)(?:\s+Alt\.?)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def build_reg_index(text: str) -> list[tuple[int, str]]:
    """Returns [(char_offset, label)] for every regulation header.
    Skips Table-of-Contents lines which contain dot sequences like ......76
    """
    index = []
    for m in REG_HEADER_RE.finditer(text):
        line = m.group(0)
        # TOC entries contain runs of 4+ dots — skip them
        if re.search(r'\.{4,}', line):
            continue
        label = re.sub(r"\s+", " ", m.group(1).strip())
        index.append((m.start(), label))
    return index


def build_reg_bodies(text: str, reg_index: list[tuple[int, str]]) -> dict[str, str]:
    """
    Returns {label: full_body_text} for every regulation.
    Body starts at the header line and runs to the next header.
    """
    bodies: dict[str, str] = {}
    for i, (offset, label) in enumerate(reg_index):
        next_offset = reg_index[i + 1][0] if i + 1 < len(reg_index) else len(text)
        body = text[offset:next_offset].strip()
        bodies[label] = body
    return bodies


def get_regulation_at(reg_index: list[tuple[int, str]], pos: int) -> str:
    label = "Preamble"
    for offset, reg in reg_index:
        if offset > pos:
            break
        label = reg
    return label


def get_paragraph_at(text: str, pos: int, look_back: int = 500) -> str:
    snippet = text[max(0, pos - look_back):pos]
    matches = list(re.finditer(
        r"^\s*(\d+(?:\s*bis|\s*ter|\s*quat\.?|\s*quin\.?)?)[\.\)]\s",
        snippet, re.MULTILINE,
    ))
    if matches:
        return f"paragraph {matches[-1].group(1).strip()}"
    return ""


def context_words(text: str, start: int, end: int, words: int = 25) -> tuple[str, str]:
    before = text[max(0, start - 400):start].replace("\n", " ")
    after  = text[end:end + 400].replace("\n", " ")
    before_snippet = " ".join(before.split()[-words:])
    after_snippet  = " ".join(after.split()[:words])
    return before_snippet, after_snippet


# ── ID helpers ────────────────────────────────────────────────────────────────

def slugify(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


def make_id(reg: str, para: str, suffix: str, seen: set) -> str:
    base = slugify(reg) + ("-" + slugify(para) if para else "") + f"-{suffix}"
    uid, n = base, 1
    while uid in seen:
        uid = f"{base}-{n}"
        n += 1
    seen.add(uid)
    return uid


# ── Type 1: [Alt.1 …] [Alt.2 …] groups ───────────────────────────────────────

ALT_OPEN_RE = re.compile(r"\[Alt[\.\s]*(\d+)[\.:\s]", re.IGNORECASE)


def extract_alt_blocks(text: str) -> list[dict]:
    blocks = []
    lines  = text.splitlines(keepends=True)
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line)

    def char_to_line(c: int) -> int:
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            offsets[mid] <= c and (lo := mid) or (hi := mid - 1)  # noqa: E701
            # plain version below is clearer:
        lo = 0
        for idx, off in enumerate(offsets):
            if off <= c:
                lo = idx
            else:
                break
        return lo

    for m in ALT_OPEN_RE.finditer(text):
        bs = m.start()
        be = find_matching_bracket(text, bs)
        if be == -1:
            continue
        blocks.append({
            "alt_num": int(m.group(1)),
            "text":    text[bs + len(m.group(0)):be].strip(),
            "start":   bs,
            "end":     be,
            "line_no": next((i for i, o in enumerate(offsets) if o > bs), len(offsets)) - 1,
        })
    return blocks


def group_alt_blocks(blocks: list[dict], line_gap: int = 8) -> list[list[dict]]:
    if not blocks:
        return []
    groups, current = [], []
    for block in blocks:
        if block["alt_num"] == 1:
            if current:
                groups.append(current)
            current = [block]
        else:
            if current and (block["line_no"] - current[-1]["line_no"]) <= line_gap:
                current.append(block)
            else:
                if current:
                    groups.append(current)
                current = [block]
    if current:
        groups.append(current)
    return [g for g in groups if len({b["alt_num"] for b in g}) >= 2]


# ── Type 2: [A] / [B] slash alternatives ─────────────────────────────────────

def extract_slash_alts(text: str, reg_index: list, reg_bodies: dict, seen: set) -> list[dict]:
    """
    Find [A] / [B] patterns using bracket-aware matching so that
    nested brackets (e.g. [New EIS [or Revision...]] / [Revision for change...])
    are handled correctly.
    """
    results = []
    i = 0
    while i < len(text) - 4:
        if text[i] != "[":
            i += 1
            continue
        # Find matching close bracket for option A
        end_a = find_matching_bracket(text, i)
        if end_a == -1:
            i += 1
            continue
        # Check if ' / [' follows
        rest = text[end_a + 1:]
        slash_m = re.match(r"\s*/\s*\[", rest)
        if not slash_m:
            i += 1
            continue

        opt_a = text[i + 1:end_a].strip()
        # Find matching close bracket for option B
        start_b = end_a + 1 + slash_m.end() - 1  # position of the '[' of option B
        end_b = find_matching_bracket(text, start_b)
        if end_b == -1:
            i += 1
            continue

        opt_b = text[start_b + 1:end_b].strip()

        # Skip trivial pure-number pairs [30] / [90]
        if re.match(r"^\d+$", opt_a) and re.match(r"^\d+$", opt_b):
            i = end_b + 1
            continue
        # Skip very short noise
        if len(opt_a) < 4 and len(opt_b) < 4:
            i = end_b + 1
            continue

        reg   = get_regulation_at(reg_index, i)
        para  = get_paragraph_at(text, i)
        uid   = make_id(reg, para, "slash", seen)
        before, after = context_words(text, i, end_b)

        results.append({
            "id":               uid,
            "regulation":       reg,
            "paragraph":        para,
            "type":             "slash",
            "options": [
                {"label": "Option A", "text": re.sub(r"\s+", " ", opt_a)},
                {"label": "Option B", "text": re.sub(r"\s+", " ", opt_b)},
            ],
            "context_before":   before,
            "context_after":    after,
            "regulation_text":  reg_bodies.get(reg, ""),
        })
        i = end_b + 1
    return results


# ── Type 3: [N. Alt. …] alternative paragraphs ───────────────────────────────

# Matches brackets that start with a paragraph number followed by Alt.
# e.g. [5. Alt. The Authority shall...], [1. bis. Alt. Where the Secretary-General...]
BRACKET_PARA_ALT_RE = re.compile(
    r"\[(\d+(?:[\s\.]*(?:bis|ter|quat|quin))?[\s\.]*Alt\..*?\])",
    re.IGNORECASE | re.DOTALL,
)


def extract_para_alts(text: str, reg_index: list, reg_bodies: dict, seen: set) -> list[dict]:
    results = []
    # Use bracket-aware matching: find [ then scan to matching ]
    for m in re.finditer(r"\[\d+[\s\.]*(?:bis|ter|quat|quin)?[\s\.]*Alt[\.\s]", text, re.IGNORECASE):
        bs = m.start()
        be = find_matching_bracket(text, bs)
        if be == -1:
            continue
        full_text = text[bs:be + 1]
        inner     = text[bs + 1:be].strip()

        # Also find the "base" paragraph (the non-Alt version of the same number)
        para_num_m = re.match(r"(\d+[\s\.]*(?:bis|ter|quat|quin)?)", inner, re.IGNORECASE)
        base_para  = para_num_m.group(1).strip() if para_num_m else ""

        reg   = get_regulation_at(reg_index, bs)
        para  = get_paragraph_at(text, bs)
        uid   = make_id(reg, f"para-alt-{base_para}", "bracket-alt", seen)
        before, after = context_words(text, bs, be)

        # Try to find the base paragraph text (the non-[Alt] version)
        base_text = ""
        if base_para:
            # Look for "N. text" (not bracketed) within the same regulation body
            reg_body = reg_bodies.get(reg, "")
            base_m = re.search(
                rf"^{re.escape(base_para)}[\.\)]\s(.+?)(?=^\d|\Z)",
                reg_body, re.MULTILINE | re.DOTALL,
            )
            if base_m:
                base_text = re.sub(r"\s+", " ", base_m.group(0).strip())[:800]

        alt_label = re.sub(r"\s+", " ", inner[:60]).strip()

        results.append({
            "id":               uid,
            "regulation":       reg,
            "paragraph":        para or f"paragraph {base_para}",
            "type":             "para_alt",
            "options": [
                {"label": "Main text",      "text": base_text or "(see regulation text)"},
                {"label": alt_label + "…",  "text": re.sub(r"\s+", " ", inner)},
            ],
            "context_before":   before,
            "context_after":    after,
            "regulation_text":  reg_bodies.get(reg, ""),
        })
    return results


# ── Type 4a: optional/new standalone paragraphs [N. text] ────────────────────

# Matches a bracket opening followed by a paragraph number+period then text
# that does NOT start with "Alt." — these are entirely optional new paragraphs
OPTIONAL_PARA_OPEN_RE = re.compile(
    r"\[(\d+(?:[\s\.]*(?:bis|ter|quat(?:er)?|quin))?[\s\.]+)(?!Alt\.)",
    re.IGNORECASE,
)

def extract_optional_paras(
    text: str, reg_index: list, reg_bodies: dict, seen: set
) -> list[dict]:
    """
    Capture fully-bracketed optional paragraphs: [N. text ...].
    These are paragraphs entirely enclosed in brackets whose removal or
    retention is still open — member states vote 'Include' vs 'Delete'.

    Heuristic filters to avoid noise:
      - Must be ≥ 60 chars inside the bracket
      - Must NOT already be labelled 'Alt.' (those are Type 3)
      - Must NOT be a pure numeral or date
    """
    results = []
    for m in OPTIONAL_PARA_OPEN_RE.finditer(text):
        bs = m.start()
        be = find_matching_bracket(text, bs)
        if be == -1:
            continue
        inner = text[bs + 1:be].strip()

        # Skip short noise and Alt. paragraphs (handled by Type 3)
        if len(inner) < 60:
            continue
        if re.match(r"\d+[\s\.]*(?:bis|ter|quat|quin)?[\s\.]*Alt\.", inner, re.IGNORECASE):
            continue

        # Extract the paragraph label (e.g. "2. bis", "4", "1. ter")
        para_label_m = re.match(
            r"(\d+(?:[\s\.]*(?:bis|ter|quat(?:er)?|quin))?)",
            inner, re.IGNORECASE
        )
        para_label = para_label_m.group(1).strip().rstrip(".").strip() if para_label_m else ""

        reg   = get_regulation_at(reg_index, bs)
        para  = f"paragraph {para_label}" if para_label else get_paragraph_at(text, bs)
        uid   = make_id(reg, f"opt-{para_label}", "optional", seen)
        before, after = context_words(text, bs, be)

        results.append({
            "id":               uid,
            "regulation":       reg,
            "paragraph":        para,
            "type":             "optional_para",
            "options": [
                {"label": "Include", "text": re.sub(r"\s+", " ", inner)},
                {"label": "Delete",  "text": "(Remove this paragraph entirely)"},
            ],
            "context_before":   before,
            "context_after":    after,
            "regulation_text":  reg_bodies.get(reg, ""),
        })
    return results


# ── Type 4: full-regulation Alt. blocks ──────────────────────────────────────

FULL_REG_ALT_RE = re.compile(
    r"^(Regulation\s+(\d+[\w\s\.]*?)\s+Alt\.?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_full_reg_alts(text: str, reg_index: list, reg_bodies: dict, seen: set) -> list[dict]:
    results = []
    for m in FULL_REG_ALT_RE.finditer(text):
        alt_header = m.group(1).strip()
        reg_num    = m.group(2).strip()
        base_label = f"Regulation {reg_num}"

        block_start = m.end()
        next_m = re.search(r"^Regulation\s+\d", text[block_start:], re.MULTILINE | re.IGNORECASE)
        block_end = block_start + next_m.start() if next_m else len(text)
        alt_text  = text[block_start:block_end].strip()

        base_body = reg_bodies.get(base_label, "")
        uid = make_id(base_label, "full-regulation", "full-reg", seen)
        before, after = context_words(text, m.start(), block_end)

        results.append({
            "id":               uid,
            "regulation":       base_label,
            "paragraph":        "full regulation",
            "type":             "full_regulation",
            "options": [
                {"label": "Main text",  "text": re.sub(r"\s+", " ", base_body[:2000])},
                {"label": alt_header,   "text": re.sub(r"\s+", " ", alt_text[:2000])},
            ],
            "context_before":   before,
            "context_after":    after,
            "regulation_text":  base_body,
        })
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    src = TEXT_DIR / f"{SOURCE_ID}.txt"
    if not src.exists():
        print(f"ERROR: {src} not found. Run scripts/ingest_pdfs.py first.")
        sys.exit(1)

    print(f"Reading {src.name} ({src.stat().st_size:,} bytes)...")
    raw  = src.read_text(encoding="utf-8")
    # Remove page markers — they break paragraph continuity
    text = re.sub(r"\[Page \d+\]\n?", "", raw)

    print("Building regulation index & bodies...")
    reg_index = build_reg_index(text)
    reg_bodies = build_reg_bodies(text, reg_index)
    print(f"  {len(reg_index)} regulation headers, {len(reg_bodies)} bodies.")

    seen_ids: set[str] = set()
    alternatives: list[dict] = []

    # ── Type 1: [Alt.1] [Alt.2] ──
    print("Extracting [Alt.N] groups...")
    alt_blocks = extract_alt_blocks(text)
    groups = group_alt_blocks(alt_blocks)
    print(f"  {len(alt_blocks)} blocks → {len(groups)} groups.")

    for idx, group in enumerate(groups):
        gs = group[0]["start"]
        ge = group[-1]["end"]
        reg  = get_regulation_at(reg_index, gs)
        para = get_paragraph_at(text, gs)
        uid  = make_id(reg, para, f"alt-{idx}", seen_ids)
        before, after = context_words(text, gs, ge)

        options = [
            {"label": f"Alt.{b['alt_num']}", "text": re.sub(r"\s+", " ", b["text"].strip())}
            for b in sorted(group, key=lambda b: b["alt_num"])
        ]
        alternatives.append({
            "id":               uid,
            "regulation":       reg,
            "paragraph":        para,
            "type":             "inline",
            "options":          options,
            "context_before":   before,
            "context_after":    after,
            "regulation_text":  reg_bodies.get(reg, ""),
        })

    # ── Type 2: [A] / [B] ──
    print("Extracting [A] / [B] slash alternatives...")
    slash_alts = extract_slash_alts(text, reg_index, reg_bodies, seen_ids)
    print(f"  {len(slash_alts)} slash alternatives.")
    alternatives.extend(slash_alts)

    # ── Type 3: [N. Alt. …] ──
    print("Extracting [N. Alt. …] paragraph alternatives...")
    para_alts = extract_para_alts(text, reg_index, reg_bodies, seen_ids)
    print(f"  {len(para_alts)} paragraph alternatives.")
    alternatives.extend(para_alts)

    # ── Type 4: Regulation N Alt. ──
    print("Extracting full-regulation alternates...")
    full_reg_alts = extract_full_reg_alts(text, reg_index, reg_bodies, seen_ids)
    print(f"  {len(full_reg_alts)} full-regulation alternates.")
    alternatives.extend(full_reg_alts)

    # ── Type 5: [N. text] optional paragraphs ──
    print("Extracting [N. text] optional paragraphs...")
    opt_paras = extract_optional_paras(text, reg_index, reg_bodies, seen_ids)
    print(f"  {len(opt_paras)} optional paragraphs.")
    alternatives.extend(opt_paras)

    # Sort by regulation number
    def sort_key(a: dict) -> tuple:
        m = re.search(r"(\d+)", a["regulation"])
        return (int(m.group(1)) if m else 999, a.get("paragraph", ""), a["type"])
    alternatives.sort(key=sort_key)

    counts = {t: sum(1 for a in alternatives if a["type"] == t)
              for t in ("inline", "slash", "para_alt", "full_regulation", "optional_para")}

    out = {
        "generated":          str(date.today()),
        "source_document":    SOURCE_REF,
        "source_file":        SOURCE_ID,
        "total":              len(alternatives),
        "counts_by_type":     counts,
        "alternatives":       alternatives,
    }

    dest = DATA_DIR / "alternatives.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. {len(alternatives)} alternatives → {dest.name} ({dest.stat().st_size:,} bytes)")
    for t, n in counts.items():
        print(f"  {n:3}  {t}")


if __name__ == "__main__":
    main()
