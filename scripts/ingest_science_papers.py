"""
Ingest peer-reviewed DSM science papers from local Zotero PDFs.

Reads dsm_papers_filepaths.csv, deduplicates, extracts text via pdfplumber,
chunks into ~700-word overlapping segments, and writes:

    data/science_papers.json   — metadata + all chunk texts (committed to git)

Usage:
    cd /path/to/ISA\ App
    python3 scripts/ingest_science_papers.py

Run once; re-run with --force to rebuild from scratch.
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CSV_PATH = Path.home() / "Downloads" / "files" / "dsm_papers_filepaths.csv"
OUT_PATH = DATA_DIR / "science_papers.json"

# Chunk parameters
CHUNK_WORDS    = 700   # target words per chunk
OVERLAP_WORDS  = 100   # word overlap between consecutive chunks
MIN_CHUNK_WORDS = 80   # discard chunks shorter than this (often just headers)
MAX_PAGES      = 120   # cap very large PDFs to avoid multi-hour extraction


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", t.lower().strip())


def authors_short(authors_str: str) -> str:
    """Return 'LastName et al.' or 'LastName & LastName' for the citation label."""
    parts = [a.strip() for a in authors_str.split(";") if a.strip()]
    if not parts:
        return "Unknown"
    first_last = parts[0].split(",")[0].strip()
    if len(parts) == 1:
        return first_last
    if len(parts) == 2:
        second_last = parts[1].split(",")[0].strip()
        return f"{first_last} & {second_last}"
    return f"{first_last} et al."


def dedup_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Remove title-near-duplicates from the CSV rows.
    Preserves sequentially numbered items (#1, #2, …) and multi-part papers.
    Returns (unique_rows, removed_titles).
    """
    used: set[int] = set()
    keep: list[int] = []
    log: list[str] = []

    for i, r in enumerate(rows):
        if i in used:
            continue
        group = [i]
        for j in range(i + 1, len(rows)):
            if j in used:
                continue
            sim = SequenceMatcher(
                None,
                normalize_title(rows[i]["title"]),
                normalize_title(rows[j]["title"]),
            ).ratio()
            if sim < 0.97:
                continue
            # Guard: titles ending with different numbers (#1 vs #2) are different items
            end_i = rows[i]["title"].strip()[-3:].strip()
            end_j = rows[j]["title"].strip()[-3:].strip()
            if end_i != end_j and (
                end_i.lstrip("#").strip().isdigit() or end_j.lstrip("#").strip().isdigit()
            ):
                continue
            group.append(j)
            used.add(j)

        # Among duplicates, keep the one with the longest authors string
        best = max(group, key=lambda k: len(rows[k]["authors"]))
        keep.append(best)
        used.add(i)

        if len(group) > 1:
            removed = [rows[k]["title"][:80] for k in group if k != best]
            log.append(f"Removed as duplicate: {removed} → kept: {rows[best]['title'][:80]}")

    return [rows[i] for i in sorted(keep)], log


def extract_pdf_text(pdf_path: Path, max_pages: int = MAX_PAGES) -> str:
    """
    Extract plain text from a PDF using pdfplumber.
    Returns empty string on failure (never raises).
    """
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages = pdf.pages[:max_pages]
            parts = []
            for page in pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    parts.append(text)
            return "\n".join(parts)
    except Exception as e:
        return ""


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS,
               overlap: int = OVERLAP_WORDS) -> list[str]:
    """
    Split text into overlapping word windows.
    Returns a list of chunk strings.
    """
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = chunk_words - overlap
    for start in range(0, len(words), step):
        end = start + chunk_words
        chunk = " ".join(words[start:end])
        if len(chunk.split()) >= MIN_CHUNK_WORDS:
            chunks.append(chunk)
        if end >= len(words):
            break
    return chunks


def make_paper_id(title: str, year: str, idx: int) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", title.lower())[:40].strip("-")
    return f"p{idx:04d}-{slug}-{year or 'nd'}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest DSM science papers into science_papers.json")
    parser.add_argument("--force", action="store_true", help="Rebuild even if output exists")
    parser.add_argument("--csv", default=str(CSV_PATH), help="Path to CSV file")
    parser.add_argument("--limit", type=int, default=0, help="Process only first N papers (for testing)")
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        existing = json.loads(OUT_PATH.read_text())
        print(f"science_papers.json already exists ({existing.get('total_papers', 0)} papers, "
              f"{existing.get('total_chunks', 0)} chunks).")
        print("Use --force to rebuild.")
        return

    # ── Load CSV ──────────────────────────────────────────────────────────────
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}")
        sys.exit(1)

    with open(csv_path, encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    print(f"Loaded {len(all_rows)} rows from CSV.")

    rows, dup_log = dedup_rows(all_rows)
    print(f"After dedup: {len(rows)} unique papers ({len(all_rows) - len(rows)} removed).")
    for msg in dup_log:
        print(f"  {msg}")

    if args.limit:
        rows = rows[:args.limit]
        print(f"Limiting to first {len(rows)} papers (--limit).")

    # ── Extract + chunk ───────────────────────────────────────────────────────
    papers_meta: list[dict] = []
    all_chunks:  list[dict] = []
    failed:      list[str]  = []
    chunk_idx = 0

    for i, row in enumerate(rows):
        title   = row["title"].strip()
        authors = row["authors"].strip()
        year    = row["year"].strip()
        pdf_path = Path(row["file_path"].strip())

        paper_id = make_paper_id(title, year, i)
        auth_short = authors_short(authors)

        # Progress
        if i % 20 == 0:
            print(f"  [{i+1}/{len(rows)}] {title[:60]}…")

        if not pdf_path.exists():
            failed.append(f"File missing: {pdf_path.name}")
            continue

        raw_text = extract_pdf_text(pdf_path)
        if not raw_text.strip():
            failed.append(f"No text extracted: {pdf_path.name}")
            continue

        # Clean extracted text a bit
        clean = re.sub(r"\n{3,}", "\n\n", raw_text)  # collapse excessive blank lines
        clean = re.sub(r"[ \t]{2,}", " ", clean)      # collapse whitespace

        chunks = chunk_text(clean)

        papers_meta.append({
            "id":           paper_id,
            "title":        title,
            "authors":      authors,
            "authors_short": auth_short,
            "year":         year,
            "local_pdf":    str(pdf_path),
            "chunk_ids":    list(range(chunk_idx, chunk_idx + len(chunks))),
            "n_chunks":     len(chunks),
            "n_words":      len(clean.split()),
        })

        for c_i, chunk_text_val in enumerate(chunks):
            all_chunks.append({
                "id":           chunk_idx,
                "paper_id":     paper_id,
                "paper_title":  title,
                "authors_short": auth_short,
                "year":         year,
                "chunk_index":  c_i,
                "text":         chunk_text_val,
            })
            chunk_idx += 1

    # ── Write output ──────────────────────────────────────────────────────────
    DATA_DIR.mkdir(exist_ok=True)
    out = {
        "generated":    str(date.today()),
        "source_csv":   str(csv_path),
        "total_papers": len(papers_meta),
        "total_chunks": len(all_chunks),
        "failed":       failed,
        "papers":       papers_meta,
        "chunks":       all_chunks,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    size_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\nDone.")
    print(f"  Papers ingested: {len(papers_meta)}")
    print(f"  Chunks created:  {len(all_chunks)}")
    print(f"  Failed/skipped:  {len(failed)}")
    print(f"  Output:          {OUT_PATH} ({size_mb:.1f} MB)")
    if failed:
        print("\nFailed:")
        for f in failed[:10]:
            print(f"  {f}")


if __name__ == "__main__":
    main()
