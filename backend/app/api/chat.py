"""
Chat API — RAG-powered chat grounded strictly in ISA regulatory texts and UNCLOS.
Uses the full JSON knowledge base (documents, working groups, standards & guidelines)
as context. Supports streaming responses via SSE.
"""

import json
import os
import re
import uuid
from typing import AsyncGenerator, List, Optional

import anthropic
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert legal assistant for the International Seabed Authority (ISA) \
exploitation regulations platform. You help negotiators, member states, contractors, observers, \
and the public understand the draft regulations on exploitation of mineral resources in the Area \
(primarily polymetallic nodules).

You have access to a comprehensive knowledge base that includes:
- The full document history of the exploitation regulations (2014–2026)
- The current text: ISBA/31/C/CRP.1/Rev.2 (Further Revised Consolidated Text, February 2026)
- The clean version: ISBA/31/C/CRP.2/Rev.2
- The suspense document: ISBA/31/C/CRP.3 (outstanding/deferred provisions)
- The outstanding issues list: ISBA/31/C/CRP.4
- Full details of all intersessional working groups (Phases 1–3) and Friends of the President groups
- All 46 Standards and Guidelines (S&G) in their development pipeline
- The foundational legal framework: UNCLOS Part XI + 1994 Implementation Agreement

STRICT RULES — follow these without exception:
1. Ground every answer in the provided context. Do not hallucinate provisions or invent document references.
2. Always cite specific document references (ISBA/31/C/CRP.1/Rev.2, Part IV, DR 44, etc.) when available.
3. If a provision is bracketed [ ] or marked as having alternatives, clearly flag it as UNRESOLVED.
4. If something is in the suspense document (ISBA/31/C/CRP.3), say so explicitly.
5. Never provide legal advice — present findings from the text only.
6. If you cannot answer from the context, say: "This requires reference to the full regulatory text \
   at [URL]. The relevant provision is [DR number] in [Part]."
7. When asked about Standards & Guidelines: distinguish clearly between Standards (legally BINDING) \
   and Guidelines (recommendatory).
8. Answer in the same language as the question (the platform supports all 6 UN official languages).
9. For questions about specific regulatory text: direct users to the PDF URLs in the knowledge base.
10. Be concise, precise, and use regulatory terminology correctly.

CONTEXT FORMAT: The knowledge base follows this structure:
- DOCUMENTS: catalogue of all regulatory texts
- WORKING GROUPS: intersessional negotiation history
- STANDARDS & GUIDELINES: the 46 S&G items tied to the R&R"""


# ── Pydantic models ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    history: Optional[List[ChatMessage]] = []
    user_id: Optional[str] = None
    language: Optional[str] = "en"


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    citations: List[str] = []
    flags: List[str] = []   # "unresolved", "circular", "out_of_scope", "suspense"


# ── Full-text retrieval ───────────────────────────────────────────────────────

# Max chars to include per document excerpt
_EXCERPT_CHARS = 8_000
# Lines of context around each keyword match
_CONTEXT_LINES = 40


def _retrieve_full_text(app_state, query: str) -> str:
    """
    Search extracted PDF texts for sections relevant to the query.
    Returns formatted excerpts to append to the context.
    """
    full_texts: dict = getattr(app_state, "full_texts", {})
    if not full_texts:
        return ""

    # Build search terms from the query
    terms: list[str] = []

    # DR/regulation number patterns  e.g. "DR 81", "regulation 44", "DR44"
    for m in re.finditer(r'\bDR\s*(\d+)\b|\breg(?:ulation)?\s*(\d+)\b', query, re.IGNORECASE):
        num = m.group(1) or m.group(2)
        terms += [f"DR {num}", f"regulation {num}", f"{num}."]

    # Part references  e.g. "Part IV", "Part 4"
    for m in re.finditer(r'\bPart\s+([IVXLCDM]+|\d+)\b', query, re.IGNORECASE):
        terms.append(f"Part {m.group(1)}")

    # Annex references
    for m in re.finditer(r'\bAnnex\s+([IVXLCDM]+|\d+|[A-Z])\b', query, re.IGNORECASE):
        terms.append(f"Annex {m.group(1)}")

    # Article references
    for m in re.finditer(r'\bArticle\s+(\d+)\b', query, re.IGNORECASE):
        terms.append(f"Article {m.group(1)}")

    # Key phrases (2+ consecutive capitalised words or quoted strings)
    for m in re.finditer(r'"([^"]{4,60})"', query):
        terms.append(m.group(1))

    if not terms:
        # No specific references — return short overview of available full texts
        doc_ids = list(full_texts.keys())
        return (
            "\n─── FULL-TEXT DOCUMENTS AVAILABLE ──────────────────────────────\n"
            f"Full text extracted for: {', '.join(doc_ids)}\n"
            "(Ask about a specific regulation, Part, Annex, or Article to retrieve verbatim text.)\n"
        )

    # Prioritise current/clean text first
    priority_order = [
        "further-rev-consolidated-text-clean-isba31c-crp2-rev2-2026-02",
        "further-rev-consolidated-text-isba31c-crp1-rev2-2026-02",
        "further-rev-suspense-isba31c-crp3-2025-12",
        "isa-consolidated-part-xi-2025",
    ]
    ordered_ids = priority_order + [k for k in full_texts if k not in priority_order]

    result_parts = ["\n─── FULL-TEXT EXCERPTS (verbatim from PDFs) ─────────────────────"]
    total_chars = 0

    for doc_id in ordered_ids:
        text = full_texts.get(doc_id)
        if not text or total_chars >= _EXCERPT_CHARS * 3:
            break

        lines = text.splitlines()
        matched_ranges: list[tuple[int, int]] = []

        for term in terms:
            for i, line in enumerate(lines):
                if term.lower() in line.lower():
                    start = max(0, i - _CONTEXT_LINES // 2)
                    end   = min(len(lines), i + _CONTEXT_LINES // 2)
                    # Merge overlapping ranges
                    if matched_ranges and start <= matched_ranges[-1][1]:
                        matched_ranges[-1] = (matched_ranges[-1][0], max(end, matched_ranges[-1][1]))
                    else:
                        matched_ranges.append((start, end))

        if not matched_ranges:
            continue

        doc_label = doc_id.replace("-", " ").title()
        result_parts.append(f"\n[Source: {doc_label}]")

        for start, end in matched_ranges[:3]:   # max 3 excerpts per doc
            excerpt = "\n".join(lines[start:end])
            if total_chars + len(excerpt) > _EXCERPT_CHARS * 3:
                excerpt = excerpt[:_EXCERPT_CHARS]
            result_parts.append(f"... (lines {start+1}–{end}) ...\n{excerpt}\n...")
            total_chars += len(excerpt)

    if len(result_parts) == 1:
        result_parts.append(
            f"No verbatim matches found for: {', '.join(terms[:5])}\n"
            "(The provision may use different numbering in the extracted text.)"
        )

    result_parts.append("─────────────────────────────────────────────────────────────\n")
    return "\n".join(result_parts)


# ── Context builder ──────────────────────────────────────────────────────────

def _build_context(app_state, query: str = "") -> str:
    """
    Build a comprehensive, structured knowledge-base context from all loaded JSON files.
    This replaces the vector-search stub with structured JSON knowledge.
    """
    parts: List[str] = [
        "═══════════════════════════════════════════════════════════════",
        "  ISA EXPLOITATION REGULATIONS — KNOWLEDGE BASE",
        "  Source: ISA data files loaded at server startup",
        "═══════════════════════════════════════════════════════════════\n",
    ]

    # ── 1. Legal framework ───────────────────────────────────────────
    parts.append("─── FOUNDATIONAL LEGAL FRAMEWORK ───────────────────────────────")
    parts.append(
        "UNCLOS / LOSC (1982): 'Constitution for the oceans'. Part XI (Articles 133–191) "
        "establishes the Area as Common Heritage of Mankind, creates the ISA, sets the "
        "legal framework for exploitation.\n"
        "1994 Implementation Agreement (IA): Fundamentally reformed Part XI. "
        "PREVAILS over Part XI in case of inconsistency (Article 2(1), IA). "
        "Both interpreted and applied as a SINGLE INSTRUMENT.\n"
        "ISA Consolidated Part XI + IA (2025): Available at "
        "https://www.isa.org.jm/wp-content/uploads/2025/07/Consolidation-of-Part-XI_e-book.pdf\n"
        "Key IA modifications to UNCLOS: Technology Transfer (Art.144), Production Policies "
        "(Art.150–151), Review Conference (Art.155 deleted), Council voting (Art.161), "
        "The Enterprise (Art.170), Financial Terms (Annex III Art.13).\n"
    )

    # ── 2. Documents catalogue ───────────────────────────────────────
    parts.append("─── REGULATORY DOCUMENT CATALOGUE ──────────────────────────────")
    docs_state = getattr(app_state, "documents", {})
    all_docs = docs_state.get("documents", [])

    if all_docs:
        current_docs = [d for d in all_docs if d.get("status") == "current"]
        active_docs  = [d for d in all_docs if d.get("status") == "active"]
        superseded   = [d for d in all_docs if d.get("status") == "superseded"]

        parts.append("CURRENT TEXTS (as of March 2026):")
        for d in current_docs:
            ref  = d.get("reference") or "—"
            date = d.get("date", "")
            desc = d.get("description", "")[:200]
            url  = d.get("url_pdf") or d.get("url_web") or ""
            parts.append(f"  • {ref} ({date}): {d.get('short_title', d.get('title',''))}")
            if desc:
                parts.append(f"    {desc}")
            if url:
                parts.append(f"    PDF: {url}")
        parts.append("")

        parts.append("ACTIVE PROCESS DOCUMENTS:")
        for d in active_docs:
            ref = d.get("reference") or "—"
            parts.append(f"  • {ref} ({d.get('date','')}): {d.get('short_title', d.get('title',''))}")
        parts.append("")

        parts.append(f"SUPERSEDED TEXTS ({len(superseded)} earlier versions): "
                     + ", ".join(d.get("reference") or d.get("short_title","?") for d in superseded[:8]) + " ...")
        parts.append("")

        # Regulatory progression (list of document IDs)
        progression = docs_state.get("regulatory_text_progression", [])
        if progression:
            doc_index = {d.get("id"): d for d in all_docs if d.get("id")}
            parts.append("REGULATORY TEXT PROGRESSION (chronological):")
            for doc_id in progression:
                d = doc_index.get(doc_id)
                if d:
                    current_flag = " ← CURRENT" if d.get("status") == "current" else ""
                    parts.append(f"  {d.get('date','')} — {d.get('reference','')}: "
                                 f"{d.get('short_title', d.get('title',''))}{current_flag}")
                else:
                    parts.append(f"  {doc_id}")
            parts.append("")
    else:
        parts.append("  (documents.json not loaded — run server from repo root)\n")

    # ── 3. Working groups ────────────────────────────────────────────
    parts.append("─── INTERSESSIONAL WORKING GROUPS ───────────────────────────────")
    wg_state = getattr(app_state, "working_groups", {})
    if wg_state:
        phases = wg_state.get("phases", {})
        for ph_key, ph_data in phases.items():
            parts.append(f"\n{ph_data.get('label','').upper()} ({ph_data.get('period','')}):")
            parts.append(f"  {ph_data.get('description','')}")

        # Phase 1–2 main groups
        for wg in wg_state.get("working_groups", []):
            abbr  = wg.get("abbreviation", wg.get("name", ""))
            chair = wg.get("chair") or wg.get("facilitator") or ""
            mtgs  = len(wg.get("meetings", []))
            cov   = ", ".join(wg.get("regulations_covered", []))
            fed   = "; ".join(wg.get("fed_into", []))
            parts.append(
                f"\n  [{abbr}] {wg.get('name','')} | Chair/Facilitator: {chair}\n"
                f"   Period: {wg.get('established','')} – {wg.get('concluded','ongoing')} | "
                f"Meetings: {mtgs} | Status: {wg.get('status','')}\n"
                f"   Covers: {cov}\n"
                f"   Fed into: {fed}\n"
                f"   Key topics: {', '.join(wg.get('key_topics',[]))}"
            )

        # Phase 3 IWGs
        p3 = wg_state.get("intersessional_working_groups_phase3", {})
        if p3:
            parts.append(f"\nPHASE 3 IWGs ({p3.get('period','')}):")
            for g in p3.get("groups", []):
                facils = ", ".join(g.get("facilitators", []))
                regs   = ", ".join(g.get("draft_regulations", []))
                parts.append(f"  [{g.get('name','')}] Facilitators: {facils} | DRs: {regs}")

        # FOP
        fop = wg_state.get("friends_of_the_president", {})
        if fop:
            parts.append(f"\nFRIENDS OF THE PRESIDENT (FOP) — {fop.get('formal_reference','ISBA/30/C/5 Annex II')}:")
            parts.append(f"  New modality proposed {fop.get('modality_document',{}).get('date','28 March 2025')}")
            for g in fop.get("groups", []):
                regs = ", ".join(g.get("draft_regulations", []))
                parts.append(f"  [{g.get('name','')}] Facilitator: {g.get('facilitator','')} | DRs: {regs}")
    else:
        parts.append("  (working_groups.json not loaded)\n")
    parts.append("")

    # ── 4. Standards & Guidelines ────────────────────────────────────
    parts.append("─── STANDARDS AND GUIDELINES (S&G) ─────────────────────────────")
    sg_state = getattr(app_state, "standards_guidelines", {})
    if sg_state:
        counts = sg_state.get("summary_counts", {})
        parts.append(
            f"Total: {counts.get('total',46)} S&G items | "
            f"Prepared: {counts.get('already_prepared_isba27',10)} | "
            f"Under development: {counts.get('under_development_ltc',1)} | "
            f"ToR prepared: 2 | In suspense doc: {counts.get('in_suspense_document',5)} | "
            f"To be developed: {counts.get('to_be_developed',27)}\n"
        )
        parts.append("Phase definitions:")
        for ph, desc in sg_state.get("phases_explanation", {}).items():
            if ph != "note_brackets":
                parts.append(f"  {ph.replace('_',' ').title()}: {desc}")
        parts.append("")
        parts.append("LEGAL STATUS: Standards = legally BINDING on contractors and ISA. "
                     "Guidelines = recommendatory in nature.\n")

        # Group by phase
        items = sg_state.get("standards_and_guidelines", [])
        for phase_num in [1, 2, 3, None]:
            ph_items = [i for i in items if i.get("phase") == phase_num]
            if not ph_items:
                continue
            ph_label = f"Phase {phase_num}" if phase_num else "Phase TBD"
            prepared = [i for i in ph_items if i.get("status") == "prepared"]
            parts.append(f"{ph_label.upper()} ({len(ph_items)} items, {len(prepared)} prepared):")
            for item in ph_items:
                st   = item.get("status", "unknown").replace("_", " ")
                doc  = item.get("isba_document") or "—"
                ty   = item.get("type", "").replace("_and_", "+").replace("_", " ")
                regs = ", ".join((item.get("draft_regulations") or [])[:5])
                pdf  = item.get("url_pdf", "")
                phn  = item.get("phase_note") or ""
                parts.append(
                    f"  #{item.get('number','?')} [{st}] {item.get('short_title','')} "
                    f"({ty}) | {doc} | DRs: {regs or '—'}{' | '+phn if phn else ''}"
                    + (f"\n      PDF: {pdf}" if pdf else "")
                )
            parts.append("")

        # ISBA/27 Phase 1 docs
        p1_docs = sg_state.get("isba_27_phase1_documents", {}).get("documents", [])
        if p1_docs:
            parts.append("ALREADY PREPARED — ISBA/27 PHASE 1 DOCUMENTS (January 2022):")
            for d in p1_docs:
                parts.append(
                    f"  {d.get('isba_reference','')}: {d.get('title','')}\n"
                    f"    PDF: {d.get('url_pdf','')}"
                )
            parts.append("")
    else:
        parts.append("  (standards_guidelines.json not loaded)\n")

    parts.append("═══════════════════════════════════════════════════════════════")

    # ── 5. Full-text excerpts (query-aware) ──────────────────────────
    if query:
        parts.append(_retrieve_full_text(app_state, query))

    return "\n".join(parts)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """
    Non-streaming chat. Returns a complete response grounded in the ISA knowledge base.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured. Set this environment variable to enable chat."
        )

    context = _build_context(request.app.state, body.message)
    messages = _build_messages(body, context)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    reply_text = response.content[0].text
    thread_id  = body.thread_id or str(uuid.uuid4())

    return ChatResponse(
        reply=reply_text,
        thread_id=thread_id,
        citations=_extract_citations(reply_text),
        flags=_detect_flags(reply_text),
    )


@router.post("/stream")
async def chat_stream(request: Request, body: ChatRequest):
    """
    Streaming chat via Server-Sent Events (SSE).
    The client receives delta text events, then a final [DONE] event with metadata.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured."
        )

    context   = _build_context(request.app.state, body.message)
    messages  = _build_messages(body, context)
    thread_id = body.thread_id or str(uuid.uuid4())
    client    = anthropic.Anthropic(api_key=api_key)

    async def event_stream() -> AsyncGenerator[str, None]:
        full_text = ""
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=messages,
            ) as stream:
                for text_chunk in stream.text_stream:
                    full_text += text_chunk
                    payload = json.dumps({"type": "delta", "text": text_chunk})
                    yield f"data: {payload}\n\n"
        except Exception as e:
            err = json.dumps({"type": "error", "message": str(e)})
            yield f"data: {err}\n\n"
            return

        # Final event with metadata
        done_payload = json.dumps({
            "type":      "done",
            "thread_id": thread_id,
            "citations": _extract_citations(full_text),
            "flags":     _detect_flags(full_text),
        })
        yield f"data: {done_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_messages(body: ChatRequest, context: str) -> list:
    """Assemble the messages array for the API call."""
    messages = []
    for msg in (body.history or []):
        messages.append({"role": msg.role, "content": msg.content})

    user_content = (
        f"KNOWLEDGE BASE:\n{context}\n\n"
        f"USER QUESTION: {body.message}\n\n"
        "Answer based on the knowledge base above. Cite document references. "
        "Flag unresolved/bracketed provisions, suspense-document items, and circular dependencies."
    )
    messages.append({"role": "user", "content": user_content})
    return messages


def _detect_flags(text: str) -> List[str]:
    """Detect response flags from text content."""
    flags = []
    if re.search(r'\[.*?\]', text):
        flags.append("unresolved")
    if "suspense" in text.lower() or "crp.3" in text.lower():
        flags.append("suspense")
    if "circular" in text.lower() or "loop" in text.lower():
        flags.append("circular")
    if "cannot be answered" in text.lower() or "not in the" in text.lower():
        flags.append("out_of_scope")
    return flags


def _extract_citations(text: str) -> List[str]:
    """Extract ISA and UNCLOS document/regulation references from response text."""
    patterns = [
        r'ISBA/\d+/[A-Z]+/[^\s,\.\)]+',
        r'DR\s*\d+[\w\s\-]*',
        r'Regulation\s+\d+[\w]*',
        r'Article\s+\d+[\w]*',
        r'Part\s+[IVX]+',
        r'Annex\s+[IVX\d]+',
        r'Appendix\s+[IVX\d]+',
        r'UNCLOS',
        r'LOSC',
    ]
    citations = []
    for pattern in patterns:
        citations.extend(re.findall(pattern, text, re.IGNORECASE))
    # Deduplicate preserving order
    seen = set()
    unique = []
    for c in citations:
        key = c.strip().upper()
        if key not in seen:
            seen.add(key)
            unique.append(c.strip())
    return unique[:15]
