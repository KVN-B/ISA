"""
Extract bracketed alternatives from ISA CRP.2/Rev.2 regulatory text.

Produces data/alternatives.json with all Alt.1/Alt.2/Alt.3 groups.

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
    """
    Given text[start] == '[', return the index of the matching ']'.
    Returns -1 if not found.
    """
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return i
    return -1


# Matches the opening of an Alt block: [Alt.1, [Alt. 2, [Alt 3:, [Alt.1., etc.
ALT_OPEN_RE = re.compile(r"\[Alt[\.\s]*(\d+)[\.:\s]", re.IGNORECASE)


def extract_alt_blocks(text: str) -> list[dict]:
    """
    Find all [Alt.N ...] blocks in the text.
    Returns list of {alt_num, text, start, end, line_no}.
    """
    blocks = []
    lines  = text.splitlines(keepends=True)
    # Build char offset → line number mapping
    offsets = []
    pos = 0
    for i, line in enumerate(lines):
        offsets.append(pos)
        pos += len(line)

    def char_to_line(c: int) -> int:
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if offsets[mid] <= c:
                lo = mid
            else:
                hi = mid - 1
        return lo

    for m in ALT_OPEN_RE.finditer(text):
        bracket_start = m.start()
        bracket_end   = find_matching_bracket(text, bracket_start)
        if bracket_end == -1:
            continue
        alt_num  = int(m.group(1))
        alt_text = text[bracket_start + len(m.group(0)):bracket_end].strip()
        line_no  = char_to_line(bracket_start)
        blocks.append({
            "alt_num": alt_num,
            "text":    alt_text,
            "start":   bracket_start,
            "end":     bracket_end,
            "line_no": line_no,
        })

    return blocks


def group_alt_blocks(blocks: list[dict], line_gap: int = 6) -> list[list[dict]]:
    """
    Group Alt blocks that appear close together (within line_gap lines) into
    alternative sets. Each group must start with Alt.1.
    """
    if not blocks:
        return []

    groups: list[list[dict]] = []
    current: list[dict] = []

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
                current = [block]  # orphan non-1 alt, keep as single

    if current:
        groups.append(current)

    # Only keep groups with 2+ distinct alt numbers
    return [g for g in groups if len({b["alt_num"] for b in g}) >= 2]


# ── Regulation context ────────────────────────────────────────────────────────

REG_HEADER_RE = re.compile(
    r"^(Regulation\s+\d+[\w\s\.]*?)(?:\s+Alt\.?)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def build_reg_index(text: str) -> list[tuple[int, str]]:
    """
    Returns list of (char_offset, regulation_label) for all regulation headers.
    """
    index = []
    for m in REG_HEADER_RE.finditer(text):
        label = re.sub(r"\s+", " ", m.group(1).strip())
        index.append((m.start(), label))
    return index


def get_regulation_at(reg_index: list[tuple[int, str]], pos: int) -> str:
    label = "Preamble"
    for offset, reg in reg_index:
        if offset > pos:
            break
        label = reg
    return label


def get_paragraph_at(text: str, pos: int, look_back: int = 500) -> str:
    snippet = text[max(0, pos - look_back):pos]
    matches = list(re.finditer(r"^\s*(\d+(?:\s*bis|\s*ter|\s*quat\.?|\s*quin\.?)?)[\.\)]\s", snippet, re.MULTILINE))
    if matches:
        return f"paragraph {matches[-1].group(1).strip()}"
    return ""


def context_words(text: str, start: int, end: int, words: int = 20) -> tuple[str, str]:
    before = text[max(0, start - 300):start].replace("\n", " ")
    after  = text[end:end + 300].replace("\n", " ")
    before_words = before.split()
    after_words  = after.split()
    before_snippet = " ".join(before_words[-words:]) if before_words else ""
    after_snippet  = " ".join(after_words[:words]) if after_words else ""
    return before_snippet, after_snippet


# ── Slugify / ID ──────────────────────────────────────────────────────────────

def slugify(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


def make_id(reg: str, para: str, idx: int, seen: set) -> str:
    base = slugify(reg) + ("-" + slugify(para) if para else "") + f"-alt-{idx}"
    uid  = base
    n    = 1
    while uid in seen:
        uid = f"{base}-{n}"
        n  += 1
    seen.add(uid)
    return uid


# ── Full-regulation alternates ────────────────────────────────────────────────

FULL_REG_ALT_RE = re.compile(
    r"^(Regulation\s+(\d+[\w\s\.]*?)\s+Alt\.?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_full_reg_alts(text: str, seen: set) -> list[dict]:
    results = []
    for m in FULL_REG_ALT_RE.finditer(text):
        alt_header = m.group(1).strip()
        reg_num    = m.group(2).strip()
        base_label = f"Regulation {reg_num}"

        # Find block of Alt. regulation
        block_start = m.end()
        next_m = re.search(r"^Regulation\s+\d", text[block_start:], re.MULTILINE | re.IGNORECASE)
        block_end = block_start + next_m.start() if next_m else len(text)
        alt_text  = text[block_start:block_end].strip()

        # Find base regulation block
        base_m = None
        for bm in re.finditer(
            rf"^{re.escape(base_label)}\s*$", text, re.MULTILINE | re.IGNORECASE
        ):
            if bm.start() < m.start():
                base_m = bm
        if base_m:
            base_start = base_m.end()
            # End before the Alt. header
            base_text  = text[base_start:m.start()].strip()
        else:
            base_text  = ""

        uid = make_id(base_label, "full-regulation", 0, seen)
        before, after = context_words(text, m.start(), block_end)

        results.append({
            "id":             uid,
            "regulation":     base_label,
            "paragraph":      "full regulation",
            "type":           "full_regulation",
            "options": [
                {"label": "Main text",  "text": re.sub(r"\s+", " ", base_text[:1500])},
                {"label": alt_header,   "text": re.sub(r"\s+", " ", alt_text[:1500])},
            ],
            "context_before": before,
            "context_after":  after,
        })
    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    src = TEXT_DIR / f"{SOURCE_ID}.txt"
    if not src.exists():
        print(f"ERROR: {src} not found. Run scripts/ingest_pdfs.py first.")
        sys.exit(1)

    print(f"Reading {src.name} ({src.stat().st_size:,} bytes)...")
    text = src.read_text(encoding="utf-8")

    # Remove page markers (they break paragraph continuity)
    text_clean = re.sub(r"\[Page \d+\]\n", "", text)

    print("Building regulation index...")
    reg_index = build_reg_index(text_clean)
    print(f"  Found {len(reg_index)} regulation headers.")

    print("Extracting [Alt.N] blocks...")
    alt_blocks = extract_alt_blocks(text_clean)
    print(f"  Found {len(alt_blocks)} individual Alt blocks.")

    groups = group_alt_blocks(alt_blocks)
    print(f"  Grouped into {len(groups)} alternative sets.")

    seen_ids: set[str] = set()
    alternatives: list[dict] = []

    for idx, group in enumerate(groups):
        group_start = group[0]["start"]
        group_end   = group[-1]["end"]

        reg   = get_regulation_at(reg_index, group_start)
        para  = get_paragraph_at(text_clean, group_start)
        uid   = make_id(reg, para, idx, seen_ids)
        before, after = context_words(text_clean, group_start, group_end)

        options = []
        for block in sorted(group, key=lambda b: b["alt_num"]):
            opt_text = re.sub(r"\s+", " ", block["text"].strip())
            options.append({
                "label": f"Alt.{block['alt_num']}",
                "text":  opt_text,
            })

        alternatives.append({
            "id":             uid,
            "regulation":     reg,
            "paragraph":      para,
            "type":           "inline",
            "options":        options,
            "context_before": before,
            "context_after":  after,
        })

    # Add full-regulation alternates
    full_reg_alts = extract_full_reg_alts(text_clean, seen_ids)
    print(f"  Found {len(full_reg_alts)} full-regulation alternates.")
    alternatives.extend(full_reg_alts)

    # Sort by regulation number
    def sort_key(a: dict) -> tuple:
        m = re.search(r"(\d+)", a["regulation"])
        return (int(m.group(1)) if m else 999, a.get("paragraph", ""))
    alternatives.sort(key=sort_key)

    inline_count   = sum(1 for a in alternatives if a["type"] == "inline")
    full_reg_count = sum(1 for a in alternatives if a["type"] == "full_regulation")

    out = {
        "generated":       str(date.today()),
        "source_document": SOURCE_REF,
        "source_file":     SOURCE_ID,
        "total":           len(alternatives),
        "inline_count":    inline_count,
        "full_reg_count":  full_reg_count,
        "alternatives":    alternatives,
    }

    dest = DATA_DIR / "alternatives.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. Written {len(alternatives)} alternatives to {dest.name} "
          f"({dest.stat().st_size:,} bytes)")
    print(f"  {inline_count} inline alternatives, {full_reg_count} full-regulation alternates")


if __name__ == "__main__":
    main()
