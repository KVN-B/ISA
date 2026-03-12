"""
Regulations API — parse and serve the structured content of ISBA/31/C/CRP.1/Rev.2.
Exposes individual regulations, parts, annexes, and provision status.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter()


class ProvisionStatus(BaseModel):
    regulation_id: str
    reference: str
    title: str
    part: str
    status: str  # open | bracketed | alternative | agreed | suspended
    has_alternatives: bool
    bracket_count: int
    is_circular: bool
    notes: Optional[str] = None


@router.get("/structure")
async def get_document_structure():
    """
    Return the high-level structure of ISBA/31/C/CRP.1/Rev.2:
    parts, sections, and regulation numbers.
    This is populated by the document ingestion pipeline.
    """
    # Structure derived from ISBA/30/C/CRP.1 table of contents (256 pages)
    # Will be updated once ISBA/31/C/CRP.1/Rev.2 is ingested
    return {
        "document": "ISBA/31/C/CRP.1/Rev.2",
        "title": "Further Revised Consolidated Text",
        "date": "2026-02",
        "parts": [
            {"part": "Preamble", "regulations": []},
            {"part": "Part I — Introduction", "regulations": ["1", "2", "3", "4"]},
            {"part": "Part II — Applications for Approval of Plans of Work", "regulations": ["5-18"]},
            {"part": "Part III — Obligations of Contractors", "regulations": ["19-37"]},
            {"part": "Part IV — Protection and Preservation of the Marine Environment", "regulations": ["38-55"]},
            {"part": "Part V — Emergency Orders", "regulations": ["56-59"]},
            {"part": "Part VI — Data and Information Management", "regulations": ["60-61"]},
            {"part": "Part VII — Financial Terms of Contracts", "regulations": ["62-88"]},
            {"part": "Part VIII — Institutional Arrangements", "regulations": ["89-93"]},
            {"part": "Part IX — Standards and Guidelines", "regulations": ["94-95"]},
            {"part": "Part X — Review of Activities", "regulations": ["96 onwards"]},
            {"part": "Part XI — Inspection, Compliance and Enforcement", "regulations": ["96-onwards"]},
        ],
        "note": "Run ingest_documents.py to populate full regulation-level detail.",
    }


@router.get("/status")
async def get_provisions_status():
    """
    Return the status of all provisions: which are agreed, bracketed,
    have alternatives, or are in the suspense document.
    """
    return {
        "source": "ISBA/31/C/CRP.1/Rev.2 + ISBA/31/C/CRP.3 (Suspense Document)",
        "summary": {
            "total_regulations": "~96+",
            "bracketed": "Multiple — see suspense document ISBA/31/C/CRP.3",
            "with_alternatives": "Multiple — marked 'Alt' in the text",
            "agreed": "Partial — those without brackets or alternatives",
            "suspended": "See ISBA/31/C/CRP.3",
        },
        "note": "Run ingest_documents.py to build a provision-by-provision status index.",
    }


@router.get("/circular-dependencies")
async def get_circular_dependencies():
    """
    Return provisions identified as creating circular regulatory processes
    — i.e., provisions that reference each other without a clear termination condition,
    or impose procedural requirements with no resolution path.
    """
    return {
        "analysis_status": "pending_ingestion",
        "description": (
            "Circular dependency detection analyses each provision's cross-references "
            "and procedural chains to identify loops where: "
            "(1) Provision A requires action B, which requires condition C, "
            "which depends on Provision A being satisfied first; or "
            "(2) a regulatory process has no defined termination condition. "
            "Run ingest_documents.py then circular_detector.py to generate this report."
        ),
        "circular_provisions": [],
    }


@router.get("/outstanding-issues")
async def get_outstanding_issues():
    """
    Return the list of outstanding issues from ISBA/31/C/CRP.4.
    """
    return {
        "source": "ISBA/31/C/CRP.4 — Draft Indicative List of Outstanding Issues",
        "url": "https://isa.org.jm/wp-content/uploads/2026/02/Draft-indicative-list-of-outstanding-issues.pdf",
        "note": "Run ingest_documents.py to parse and index the outstanding issues list.",
        "issues": [],
    }
