"""
Science Anchor — Dual-RAG endpoint.

Layer 1 (Science):   BM25 retrieval over peer-reviewed DSM papers
                     → data/science_papers.json (built by scripts/ingest_science_papers.py)

Layer 2 (Regulatory): Keyword retrieval over ISA regulatory texts
                     → reuses the full-text logic from chat.py

The LLM is instructed to answer in exactly two sections — Science / Regulatory —
and must keep them strictly separate: probability language preserved in Layer 1,
specific regulation citations in Layer 2.
"""

import json
import math
import os
import re
import uuid
from collections import Counter, defaultdict
from typing import AsyncGenerator, List, Optional

import anthropic
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.chat import _build_context, _retrieve_full_text

router = APIRouter()

# ── BM25 ──────────────────────────────────────────────────────────────────────

STOPWORDS = frozenset("""
a an the is are was were be been being have has had do does did will would
could should may might shall can need of in on at to from by for with as
this that these those it its which who what where when how all any some
we our their them they he she his her also about into between during before
after both but either or nor yet so although though because since while
i we are they you your our its we the and for not with this from that have
""".split())


def _tokenize(text: str) -> list[str]:
    return [
        w for w in re.findall(r"[a-z]+", text.lower())
        if w not in STOPWORDS and len(w) > 2
    ]


class _BM25Index:
    """Lightweight in-memory BM25 index (built at startup from science_papers.json)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b  = b
        self._chunks: list[dict] = []        # raw chunk dicts from JSON
        self._token_docs: list[list[str]] = []  # tokenised version per chunk
        self._tf: list[Counter] = []            # term freq per chunk
        self._idf: dict[str, float] = {}
        self._inv: dict[str, list[int]] = defaultdict(list)  # term → chunk ids
        self._avg_dl: float = 0.0
        self._n: int = 0

    def build(self, chunks: list[dict]) -> None:
        self._chunks = chunks
        self._n = len(chunks)
        self._token_docs = [_tokenize(c["text"]) for c in chunks]
        self._tf = [Counter(td) for td in self._token_docs]

        # Avg document length (in tokens)
        self._avg_dl = sum(len(td) for td in self._token_docs) / max(1, self._n)

        # Document frequency + inverted index
        df: dict[str, int] = defaultdict(int)
        for i, td in enumerate(self._token_docs):
            for term in set(td):
                df[term] += 1
                self._inv[term].append(i)

        # IDF (Robertson–Spärck Jones)
        self._idf = {
            term: math.log(1 + (self._n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def search(self, query: str, k: int = 8) -> list[dict]:
        """Return up to k chunk dicts ranked by BM25 score."""
        if not self._n:
            return []
        q_terms = _tokenize(query)
        if not q_terms:
            return []

        # Candidates: any chunk that contains at least one query term
        candidates: set[int] = set()
        for term in q_terms:
            for idx in self._inv.get(term, []):
                candidates.add(idx)
        if not candidates:
            return []

        # Score
        scored: list[tuple[float, int]] = []
        for idx in candidates:
            tf = self._tf[idx]
            dl = len(self._token_docs[idx])
            score = 0.0
            for term in q_terms:
                idf = self._idf.get(term, 0.0)
                f   = tf.get(term, 0)
                num = f * (self.k1 + 1)
                den = f + self.k1 * (1 - self.b + self.b * dl / self._avg_dl)
                score += idf * num / den
            scored.append((score, idx))

        scored.sort(key=lambda x: -x[0])
        return [self._chunks[idx] for _, idx in scored[:k]]


# Module-level singleton (populated in load_science_index)
_science_index: _BM25Index = _BM25Index()
_science_meta: dict = {}   # {paper_id: paper_meta_dict}


def load_science_index(data_dir) -> int:
    """
    Load science_papers.json and build the BM25 index.
    Called from main.py lifespan startup.
    Returns number of chunks indexed.
    """
    global _science_index, _science_meta
    path = data_dir / "science_papers.json"
    if not path.exists():
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    chunks = data.get("chunks", [])
    papers = data.get("papers", [])

    _science_meta = {p["id"]: p for p in papers}
    _science_index.build(chunks)
    return len(chunks)


# ── Context builders ──────────────────────────────────────────────────────────

def _build_science_context(query: str, top_k: int = 7) -> str:
    """BM25 retrieval → formatted Layer 1 context block."""
    results = _science_index.search(query, k=top_k)
    if not results:
        return (
            "═══ LAYER 1 · PEER-REVIEWED SCIENCE ═══════════════════════════\n"
            "  No relevant peer-reviewed papers found for this query.\n"
            "══════════════════════════════════════════════════════════════════\n"
        )

    # Deduplicate by paper (keep best chunk per paper, then take up to top_k papers)
    seen_papers: set[str] = set()
    deduped: list[dict] = []
    for chunk in results:
        pid = chunk.get("paper_id", "")
        if pid not in seen_papers:
            deduped.append(chunk)
            seen_papers.add(pid)
        if len(deduped) >= top_k:
            break

    parts = [
        "═══ LAYER 1 · PEER-REVIEWED SCIENCE ═══════════════════════════",
        f"  {len(deduped)} most relevant papers retrieved via BM25 search.",
        "",
    ]
    for i, chunk in enumerate(deduped, 1):
        auth  = chunk.get("authors_short", "Unknown")
        year  = chunk.get("year", "n.d.")
        title = chunk.get("paper_title", "Untitled")
        text  = chunk.get("text", "")
        parts += [
            f"[S{i}] {auth} ({year}) — {title}",
            f"  EXCERPT: {text[:2400]}",
            "",
        ]
    parts.append("══════════════════════════════════════════════════════════════════")
    return "\n".join(parts)


def _build_regulatory_context(app_state, query: str) -> str:
    """Focused regulatory Layer 2: full-text excerpts + brief catalogue summary."""
    excerpts = _retrieve_full_text(app_state, query)

    # Compact document list (just references + one-line description)
    docs_state  = getattr(app_state, "documents", {})
    all_docs    = docs_state.get("documents", [])
    current_doc = next((d for d in all_docs if d.get("status") == "current"), None)
    suspense    = next((d for d in all_docs if "crp3" in (d.get("id") or "").lower()), None)
    outstanding = next((d for d in all_docs if "crp4" in (d.get("id") or "").lower()), None)

    summary_lines = [
        "═══ LAYER 2 · ISA REGULATORY FRAMEWORK ════════════════════════",
        "Current consolidated text:  "
        + (f"{current_doc['reference']} ({current_doc['date']})" if current_doc else "—"),
        "Suspense provisions:        "
        + (f"{suspense['reference']}" if suspense else "—"),
        "Outstanding issues:         "
        + (f"{outstanding['reference']}" if outstanding else "—"),
        "Legal foundation:           UNCLOS Part XI + 1994 Implementation Agreement",
        "",
        excerpts,
        "══════════════════════════════════════════════════════════════════",
    ]
    return "\n".join(summary_lines)


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are the Science Anchor — a dual-layer research assistant for the International \
Seabed Authority (ISA). You answer questions about deep-sea mining by drawing \
EXCLUSIVELY on the two provided knowledge layers below. \
You NEVER use general knowledge, outside sources, or anything not found in the context.

RESPONSE FORMAT — MANDATORY:
Divide every response into exactly two clearly labelled sections:

## 🔬 What the science says
Use ONLY the [S1], [S2], … excerpts from Layer 1 above.
• Preserve ALL probability language exactly as written in the sources: \
"may", "could", "suggests", "is likely to", "is expected to".
• State the study conditions, geographic scope, and caveats for each finding.
• Citation format: (AuthorName et al., Year) — match the [Sx] reference label.
• If no relevant peer-reviewed evidence was retrieved, write: \
"No peer-reviewed studies on this specific question were found in the indexed literature."

---

## ⚖️ What the regulatory framework provides
Use ONLY Layer 2 regulatory sources (ISA documents, UNCLOS Part XI, Standards & Guidelines).
• Cite specific provisions: [DR 44, paragraph 2], [Annex IV, section 3], [Standard S-4].
• State what the framework requires, prohibits, mandates, or permits.
• If no relevant regulatory text was retrieved, write: \
"The provided regulatory context does not directly address this question."

STRICT RULES — non-negotiable:
1. Do NOT conflate the two layers. "The science suggests X could occur" ≠ \
"Therefore X will occur" ≠ "Therefore the framework is adequate or inadequate."
2. A regulatory requirement to monitor does NOT imply the science shows monitoring is \
effective — cite both independently.
3. Do NOT use regulatory documents to support or refute scientific claims.
4. Do NOT use scientific papers to interpret regulatory text.
5. If a regulatory provision is bracketed [ ] or marked as an alternative, flag it as UNRESOLVED.
6. If a question requires information not in the provided context, say so explicitly — \
do not hallucinate citations or provisions.
7. Answer in the same language as the question (English, French, Spanish, Arabic, Chinese, Russian).\
"""


# ── Pydantic models ───────────────────────────────────────────────────────────

class ScienceMessage(BaseModel):
    role: str
    content: str


class ScienceRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    history: Optional[List[ScienceMessage]] = []


class ScienceResponse(BaseModel):
    reply: str
    thread_id: str
    science_citations: List[str] = []   # author+year strings
    regulatory_citations: List[str] = []


# ── Citation extraction ───────────────────────────────────────────────────────

def _extract_science_citations(text: str) -> list[str]:
    """Pull (Author et al., YYYY) style citations from response text."""
    return list(dict.fromkeys(
        re.findall(r"\([A-Z][^()]{2,50},\s*\d{4}\)", text)
    ))


def _extract_regulatory_citations(text: str) -> list[str]:
    """Pull [DR N …] and [Regulation N …] style references."""
    return list(dict.fromkeys(
        re.findall(r"\[(?:DR|Regulation|Part|Annex|Article|Standard)[^\]]{1,60}\]", text)
    ))


# ── Message assembly ──────────────────────────────────────────────────────────

def _assemble_messages(
    request: ScienceRequest,
    science_ctx: str,
    regulatory_ctx: str,
) -> list[dict]:
    """Build Anthropic messages list with dual-layer context prepended to user turn."""
    context_block = f"{science_ctx}\n\n{regulatory_ctx}"
    user_content  = (
        f"{context_block}\n\n"
        f"─── USER QUESTION ───────────────────────────────────────────────\n"
        f"{request.message}\n"
        f"─────────────────────────────────────────────────────────────────"
    )

    messages: list[dict] = []
    # Include conversation history (without re-injecting context)
    for msg in (request.history or []):
        messages.append({"role": msg.role, "content": msg.content})

    # Replace last user turn with context-enriched version
    messages.append({"role": "user", "content": user_content})
    return messages


# ── SSE generator ─────────────────────────────────────────────────────────────

async def _stream_response(
    client: anthropic.Anthropic,
    messages: list[dict],
    thread_id: str,
) -> AsyncGenerator[str, None]:
    full_text = ""
    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=6_000,
            system=_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            for delta in stream.text_stream:
                full_text += delta
                yield f"data: {json.dumps({'delta': delta})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return

    sci_cites = _extract_science_citations(full_text)
    reg_cites = _extract_regulatory_citations(full_text)
    done_payload = json.dumps({
        "done": True,
        "thread_id": thread_id,
        "science_citations": sci_cites,
        "regulatory_citations": reg_cites,
    })
    yield f"data: {done_payload}\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/stream")
async def science_stream(request: Request, body: ScienceRequest):
    """
    Streaming dual-RAG chat (SSE).
    Retrieves science papers (BM25) and regulatory text (keyword), then streams
    a two-section response: Science / Regulatory.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured.",
        )

    query          = body.message
    science_ctx    = _build_science_context(query)
    regulatory_ctx = _build_regulatory_context(request.app.state, query)
    messages       = _assemble_messages(body, science_ctx, regulatory_ctx)
    thread_id      = body.thread_id or str(uuid.uuid4())
    client         = anthropic.Anthropic(api_key=api_key)

    return StreamingResponse(
        _stream_response(client, messages, thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/", response_model=ScienceResponse)
async def science_query(request: Request, body: ScienceRequest):
    """Non-streaming dual-RAG query (for testing)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured.")

    query          = body.message
    science_ctx    = _build_science_context(query)
    regulatory_ctx = _build_regulatory_context(request.app.state, query)
    messages       = _assemble_messages(body, science_ctx, regulatory_ctx)
    thread_id      = body.thread_id or str(uuid.uuid4())
    client         = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6_000,
        system=_SYSTEM_PROMPT,
        messages=messages,
    )
    reply = response.content[0].text

    return ScienceResponse(
        reply=reply,
        thread_id=thread_id,
        science_citations=_extract_science_citations(reply),
        regulatory_citations=_extract_regulatory_citations(reply),
    )


@router.get("/status")
async def science_status():
    """Returns the current state of the science index."""
    n_chunks = _science_index._n
    n_papers = len(_science_meta)
    return {
        "indexed_papers": n_papers,
        "indexed_chunks": n_chunks,
        "ready": n_chunks > 0,
    }


@router.get("/papers")
async def list_papers(q: str = "", limit: int = 50, offset: int = 0):
    """Browse / search the indexed paper library by title or author."""
    papers = list(_science_meta.values())
    if q:
        ql = q.lower()
        papers = [
            p for p in papers
            if ql in p.get("title", "").lower()
            or ql in p.get("authors", "").lower()
            or ql in p.get("year", "")
        ]
    papers.sort(key=lambda p: p.get("year", "0"), reverse=True)
    return {
        "total": len(papers),
        "results": papers[offset: offset + limit],
    }
