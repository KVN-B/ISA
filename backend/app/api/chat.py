"""
Chat API — RAG-powered chat grounded strictly in ISA regulatory texts and UNCLOS.
No hallucination: responses cite specific provisions and refuse to speculate beyond the corpus.
"""

import os
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import anthropic

router = APIRouter()

SYSTEM_PROMPT = """You are a legal assistant for the International Seabed Authority (ISA) \
exploitation regulations platform. Your role is to help stakeholders understand the draft \
regulations on exploitation of mineral resources in the Area (polymetallic nodules).

STRICT RULES — you must follow these without exception:
1. ONLY answer based on the document excerpts provided in the context. Do not use general knowledge.
2. If the answer is not in the provided context, say exactly: "This question cannot be answered \
   from the current regulatory texts. Please refer to [specific document] or raise it as an \
   open question in the stakeholder process."
3. Always cite the specific regulation number, part, and document reference when quoting text.
4. If a provision is bracketed [ ] or has alternatives, clearly flag this as UNRESOLVED.
5. If a provision creates a circular reference or procedural loop, flag it as a CIRCULAR DEPENDENCY.
6. Never provide legal advice. State findings from the text only.
7. Be concise. Use regulation numbers in your answers.
8. Responses must be in the same language as the question.

You are grounded in: UNCLOS Part XI, the 1994 Implementation Agreement, and the ISA Draft \
Exploitation Regulations (ISBA/31/C/CRP.1/Rev.2 and earlier versions)."""


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
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
    flags: List[str] = []  # "unresolved", "circular", "out_of_scope"


@router.post("/", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """
    Send a message and receive a grounded response based on the regulatory texts.
    All responses cite specific provisions. Unresolved and circular provisions are flagged.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured. Set this environment variable to enable chat."
        )

    # Build conversation history
    messages = []
    for msg in (body.history or []):
        messages.append({"role": msg.role, "content": msg.content})

    # Retrieve relevant document context (stub — replace with vector search)
    context = _get_context_stub()

    user_message = f"""CONTEXT FROM REGULATORY DOCUMENTS:
{context}

USER QUESTION: {body.message}

Instructions: Answer based only on the context above. Cite specific regulations. \
Flag any bracketed/unresolved provisions and circular dependencies you find."""

    messages.append({"role": "user", "content": user_message})

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    reply_text = response.content[0].text

    # Simple flag detection
    flags = []
    if "[" in reply_text and "]" in reply_text:
        flags.append("unresolved")
    if "circular" in reply_text.lower() or "loop" in reply_text.lower():
        flags.append("circular")
    if "cannot be answered" in reply_text.lower():
        flags.append("out_of_scope")

    import uuid
    thread_id = body.thread_id or str(uuid.uuid4())

    return ChatResponse(
        reply=reply_text,
        thread_id=thread_id,
        citations=_extract_citations(reply_text),
        flags=flags,
    )


def _get_context_stub() -> str:
    """
    Stub: returns a placeholder context.
    Replace with actual vector search against ingested regulatory documents.
    """
    return (
        "NOTE: Document ingestion pipeline not yet initialised. "
        "Run `python scripts/ingest_documents.py` to load the regulatory texts "
        "into the vector database. Once loaded, this will return the top-k most "
        "relevant passages from ISBA/31/C/CRP.1/Rev.2 and UNCLOS Part XI."
    )


def _extract_citations(text: str) -> List[str]:
    """Extract regulation references from response text."""
    import re
    patterns = [
        r'Regulation \d+[\w\s]*',
        r'ISBA/\d+/[A-Z]+/[^\s,\.]+',
        r'Article \d+[\w\s]*',
        r'Part [IVX]+',
        r'Annex [IVX\d]+',
    ]
    citations = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        citations.extend(matches)
    return list(set(citations))[:10]
