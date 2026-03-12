"""
ISA Document Ingestion Pipeline
================================
Downloads and ingests the key ISA regulatory documents into a ChromaDB
vector database for use by the RAG chat system.

Documents ingested:
  - ISBA/31/C/CRP.1/Rev.2  — Further Revised Consolidated Text (CURRENT)
  - ISBA/31/C/CRP.3        — Further Revised Suspense Document
  - ISBA/31/C/CRP.4        — Outstanding Issues List
  - ISBA/30/C/CRP.1        — Revised Consolidated Text (for comparison)
  - UNCLOS Part XI         — Foundation legal text

Usage:
  pip install -r requirements.txt
  ANTHROPIC_API_KEY=your_key python scripts/ingest_documents.py
"""

import os
import re
import json
import hashlib
import tempfile
from pathlib import Path
from typing import List, Dict

import httpx
import pdfplumber
import chromadb
from chromadb.utils import embedding_functions

DOCUMENTS_TO_INGEST = [
    {
        "id": "isba-31-c-crp1-rev2",
        "reference": "ISBA/31/C/CRP.1/Rev.2",
        "title": "Further Revised Consolidated Text",
        "url": "https://isa.org.jm/wp-content/uploads/2026/02/Further-Revised-Consolidated-Text.pdf",
        "is_primary": True,
    },
    {
        "id": "isba-31-c-crp3",
        "reference": "ISBA/31/C/CRP.3",
        "title": "Further Revised Suspense Document",
        "url": "https://isa.org.jm/wp-content/uploads/2025/12/Further-Revised-Suspense-Document.pdf",
        "is_primary": False,
    },
    {
        "id": "isba-31-c-crp4",
        "reference": "ISBA/31/C/CRP.4",
        "title": "Draft Indicative List of Outstanding Issues",
        "url": "https://isa.org.jm/wp-content/uploads/2026/02/Draft-indicative-list-of-outstanding-issues.pdf",
        "is_primary": False,
    },
    {
        "id": "isba-30-c-crp1",
        "reference": "ISBA/30/C/CRP.1",
        "title": "Revised Consolidated Text (Session 30)",
        "url": "https://isa.org.jm/wp-content/uploads/2025/01/29112024-Revised-Consolidated-Text.pdf",
        "is_primary": False,
    },
]

CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
COLLECTION_NAME = "isa_regulations"


def download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF from the ISA website."""
    try:
        print(f"  Downloading: {url}")
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
        print(f"  Saved: {dest} ({dest.stat().st_size / 1024:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ERROR downloading {url}: {e}")
        return False


def extract_chunks(pdf_path: Path, doc_id: str, reference: str, title: str) -> List[Dict]:
    """
    Extract text chunks from a PDF, preserving regulation boundaries.
    Each chunk = one regulation or section.
    """
    chunks = []
    reg_pattern = re.compile(r'^Regulation\s+(\d+[\w\s]*)', re.MULTILINE)
    part_pattern = re.compile(r'^Part\s+([IVX]+\s+[-–]?\s*.+)$', re.MULTILINE)

    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        page_map = []  # (char_offset, page_num)
        offset = 0
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            full_text += text + "\n"
            page_map.append((offset, i + 1))
            offset += len(text) + 1

    # Split by regulation boundaries
    segments = re.split(r'(?=^Regulation\s+\d+)', full_text, flags=re.MULTILINE)

    current_part = "Preamble"
    for seg in segments:
        if not seg.strip():
            continue

        # Detect part headers
        part_match = part_pattern.search(seg)
        if part_match:
            current_part = part_match.group(0).strip()

        # Detect regulation number
        reg_match = reg_pattern.match(seg.strip())
        regulation_ref = reg_match.group(1).strip() if reg_match else None

        # Detect brackets and alternatives
        bracket_count = seg.count('[')
        has_alt = bool(re.search(r'Regulation \d+\s+Alt', seg))
        is_bracketed = bracket_count > 0

        # Split long segments into sub-chunks (~500 words)
        words = seg.split()
        chunk_size = 500
        for i in range(0, max(1, len(words)), chunk_size):
            chunk_text = " ".join(words[i:i + chunk_size])
            if len(chunk_text.strip()) < 50:
                continue

            chunk_id = hashlib.md5(f"{doc_id}:{regulation_ref}:{i}:{chunk_text[:50]}".encode()).hexdigest()[:16]
            chunks.append({
                "id": f"{doc_id}_{chunk_id}",
                "text": chunk_text,
                "metadata": {
                    "doc_id": doc_id,
                    "reference": reference,
                    "title": title,
                    "part": current_part,
                    "regulation": regulation_ref or "general",
                    "is_bracketed": str(is_bracketed),
                    "bracket_count": str(bracket_count),
                    "has_alternative": str(has_alt),
                    "chunk_index": str(i // chunk_size),
                },
            })

    print(f"  Extracted {len(chunks)} chunks from {pdf_path.name}")
    return chunks


def ingest_to_chroma(chunks: List[Dict], collection):
    """Add chunks to ChromaDB collection in batches."""
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
    print(f"  Ingested {len(chunks)} chunks into ChromaDB.")


def main():
    print("=" * 60)
    print("ISA Regulation Document Ingestion Pipeline")
    print("=" * 60)

    # Set up ChromaDB
    CHROMA_PATH.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    ef = embedding_functions.DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"description": "ISA exploitation regulations corpus"},
    )

    existing_ids = set(collection.get()["ids"])
    print(f"Existing chunks in DB: {len(existing_ids)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        for doc in DOCUMENTS_TO_INGEST:
            print(f"\n--- {doc['reference']}: {doc['title']} ---")
            pdf_path = tmpdir / f"{doc['id']}.pdf"

            if not download_pdf(doc["url"], pdf_path):
                print(f"  Skipping {doc['reference']} due to download error.")
                continue

            chunks = extract_chunks(pdf_path, doc["id"], doc["reference"], doc["title"])

            # Only add new chunks
            new_chunks = [c for c in chunks if c["id"] not in existing_ids]
            if new_chunks:
                ingest_to_chroma(new_chunks, collection)
                existing_ids.update(c["id"] for c in new_chunks)
            else:
                print(f"  All chunks already present, skipping.")

    print(f"\nIngestion complete. Total chunks in DB: {collection.count()}")
    print(f"ChromaDB stored at: {CHROMA_PATH}")


if __name__ == "__main__":
    main()
