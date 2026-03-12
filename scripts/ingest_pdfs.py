"""
Ingest PDF text from ISA regulatory documents.

Downloads PDFs for current/in_force documents and extracts their text,
saving each to data/full_texts/{doc_id}.txt

Usage:
    cd /path/to/ISA\ App
    pip3 install pdfplumber requests
    python3 scripts/ingest_pdfs.py
"""

import json
import sys
from pathlib import Path

import pdfplumber
import requests

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
TEXT_DIR = DATA_DIR / "full_texts"
TEXT_DIR.mkdir(exist_ok=True)

# Documents to ingest (by status)
TARGET_STATUSES = {"current", "in_force"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def download_pdf(url: str, dest: Path) -> bool:
    try:
        print(f"    Downloading {url[:80]}...")
        r = requests.get(url, timeout=120, headers=HEADERS)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"    Downloaded {len(r.content):,} bytes")
        return True
    except Exception as e:
        print(f"    ERROR downloading: {e}")
        return False


def extract_text(pdf_path: Path) -> str:
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                t = page.extract_text()
                if t and t.strip():
                    parts.append(f"[Page {i + 1}]\n{t.strip()}")
    except Exception as e:
        print(f"    ERROR extracting text: {e}")
    return "\n\n".join(parts)


def ingest(force: bool = False):
    docs_path = DATA_DIR / "documents.json"
    if not docs_path.exists():
        print("ERROR: data/documents.json not found. Run from repo root.")
        sys.exit(1)

    docs = json.loads(docs_path.read_text())["documents"]
    def get_pdf_url(doc: dict) -> str:
        """Return best available PDF URL for a document."""
        return (
            doc.get("url_pdf")
            or doc.get("url_pdf_en")
            or ""
        )

    targets = [
        d for d in docs
        if d.get("status") in TARGET_STATUSES and get_pdf_url(d)
    ]

    print(f"Found {len(targets)} documents to ingest.\n")

    results = {"ok": [], "skip": [], "fail": []}

    for doc in targets:
        doc_id   = doc["id"]
        ref      = doc.get("reference") or doc_id
        pdf_url  = get_pdf_url(doc)
        text_path = TEXT_DIR / f"{doc_id}.txt"

        print(f"[{ref}] {doc_id}")

        if text_path.exists() and not force:
            size = text_path.stat().st_size
            print(f"  SKIP — already extracted ({size:,} bytes)\n")
            results["skip"].append(doc_id)
            continue

        tmp_pdf = TEXT_DIR / f"_tmp_{doc_id}.pdf"
        try:
            if not download_pdf(pdf_url, tmp_pdf):
                results["fail"].append(doc_id)
                print()
                continue

            text = extract_text(tmp_pdf)
            if not text.strip():
                print("  WARNING: no text extracted (scanned PDF?)")
                results["fail"].append(doc_id)
                print()
                continue

            text_path.write_text(text, encoding="utf-8")
            print(f"  OK — {len(text):,} chars, {text.count(chr(10)):,} lines\n")
            results["ok"].append(doc_id)

        finally:
            if tmp_pdf.exists():
                tmp_pdf.unlink()

    print("─" * 60)
    print(f"Done.  OK: {len(results['ok'])}  "
          f"Skipped: {len(results['skip'])}  "
          f"Failed: {len(results['fail'])}")
    if results["fail"]:
        print(f"Failed: {results['fail']}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    ingest(force=force)
