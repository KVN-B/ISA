"""
Documents API — list, filter, and retrieve ISA regulatory documents.
"""

from fastapi import APIRouter, Request, Query
from typing import Optional, List

router = APIRouter()


@router.get("/")
async def list_documents(
    request: Request,
    type: Optional[str] = Query(None, description="Filter by document type"),
    status: Optional[str] = Query(None, description="Filter by status: current|active|superseded|historical"),
    session: Optional[int] = Query(None, description="Filter by ISA session number"),
    q: Optional[str] = Query(None, description="Text search in title and description"),
):
    """Return all documents, with optional filters."""
    docs = request.app.state.documents.get("documents", [])

    if type:
        type_map = {
            "main": ["main_regulatory_text", "clean_version"],
            "companion": ["companion_document", "briefing_note", "standards_guidelines"],
            "stakeholder": ["stakeholder_submission"],
            "process": ["road_map"],
            "discussion": ["discussion_paper"],
        }
        allowed = type_map.get(type, [type])
        docs = [d for d in docs if d.get("type") in allowed]

    if status:
        docs = [d for d in docs if d.get("status") == status]

    if session:
        docs = [d for d in docs if d.get("session") == session]

    if q:
        q_lower = q.lower()
        docs = [
            d for d in docs
            if q_lower in d.get("title", "").lower()
            or q_lower in d.get("description", "").lower()
            or q_lower in " ".join(d.get("key_topics", [])).lower()
            or q_lower in (d.get("reference") or "").lower()
        ]

    return {
        "total": len(docs),
        "documents": sorted(docs, key=lambda d: d.get("date_sort", ""), reverse=True),
    }


@router.get("/current")
async def get_current_documents(request: Request):
    """Return only the most current active documents."""
    docs = request.app.state.documents.get("documents", [])
    current = [d for d in docs if d.get("status") in ("current", "active")]
    return {"total": len(current), "documents": current}


@router.get("/progression")
async def get_regulatory_progression(request: Request):
    """Return the main regulatory text progression from first draft to current."""
    progression_ids = request.app.state.documents.get("regulatory_text_progression", [])
    all_docs = {d["id"]: d for d in request.app.state.documents.get("documents", [])}
    progression = [all_docs[pid] for pid in progression_ids if pid in all_docs]
    return {"total": len(progression), "documents": progression}


@router.get("/sessions")
async def get_sessions_metadata(request: Request):
    """Return metadata for all ISA sessions."""
    return request.app.state.documents.get("sessions_metadata", {})


@router.get("/{doc_id}")
async def get_document(doc_id: str, request: Request):
    """Return a single document by ID."""
    docs = request.app.state.documents.get("documents", [])
    doc = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    return doc
