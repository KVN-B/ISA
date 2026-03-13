"""
ISA Exploitation Regulations App — FastAPI Backend
International Seabed Authority · Polymetallic Nodules
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import alternatives, chat, documents, regulations

# DATA_DIR can be overridden via environment variable for production deployments.
# Falls back to the repo's data/ folder for local development.
_default_data = Path(__file__).parent.parent.parent / "data"
DATA_DIR = Path(os.environ.get("DATA_DIR", str(_default_data)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load all data catalogues into app state."""

    # Documents catalogue
    docs_path = DATA_DIR / "documents.json"
    if docs_path.exists():
        with open(docs_path) as f:
            app.state.documents = json.load(f)
        n = len(app.state.documents.get("documents", []))
        print(f"✅  Loaded {n} documents from documents.json")
    else:
        app.state.documents = {"documents": []}
        print("⚠️   documents.json not found.")

    # Working groups
    wg_path = DATA_DIR / "working_groups.json"
    if wg_path.exists():
        with open(wg_path) as f:
            app.state.working_groups = json.load(f)
        n = len(app.state.working_groups.get("working_groups", []))
        print(f"✅  Loaded working groups data ({n} main groups + Phase 3 + FOP)")
    else:
        app.state.working_groups = {}
        print("⚠️   working_groups.json not found.")

    # Standards & Guidelines
    sg_path = DATA_DIR / "standards_guidelines.json"
    if sg_path.exists():
        with open(sg_path) as f:
            app.state.standards_guidelines = json.load(f)
        n = app.state.standards_guidelines.get("summary_counts", {}).get("total", 0)
        print(f"✅  Loaded {n} standards and guidelines from standards_guidelines.json")
    else:
        app.state.standards_guidelines = {}
        print("⚠️   standards_guidelines.json not found.")

    # Full text extracts (from scripts/ingest_pdfs.py)
    full_texts_dir = DATA_DIR / "full_texts"
    full_texts: dict[str, str] = {}
    if full_texts_dir.exists():
        for txt_file in full_texts_dir.glob("*.txt"):
            doc_id = txt_file.stem
            full_texts[doc_id] = txt_file.read_text(encoding="utf-8")
        if full_texts:
            print(f"✅  Loaded full text for {len(full_texts)} documents")
        else:
            print("ℹ️   No extracted texts found (run scripts/ingest_pdfs.py)")
    app.state.full_texts = full_texts

    # Alternatives (from scripts/extract_alternatives.py)
    alts_path = DATA_DIR / "alternatives.json"
    if alts_path.exists():
        with open(alts_path) as f:
            app.state.alternatives = json.load(f)
        n = app.state.alternatives.get("total", 0)
        print(f"✅  Loaded {n} alternatives from alternatives.json")
    else:
        app.state.alternatives = {"alternatives": []}
        print("ℹ️   alternatives.json not found (run scripts/extract_alternatives.py)")

    yield   # server runs here


app = FastAPI(
    title="ISA Exploitation Regulations API",
    description=(
        "API for the International Seabed Authority draft exploitation regulations platform. "
        "Provides document catalogue, RAG chat, and regulation analysis endpoints."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve chat.html and timeline.html from the project root
ROOT_DIR = Path(__file__).parent.parent.parent
app.mount("/static", StaticFiles(directory=str(ROOT_DIR)), name="static")

app.include_router(documents.router,     prefix="/api/documents",   tags=["Documents"])
app.include_router(chat.router,          prefix="/api/chat",        tags=["Chat"])
app.include_router(regulations.router,   prefix="/api/regulations", tags=["Regulations"])
app.include_router(alternatives.router,  prefix="/api",             tags=["Alternatives"])


@app.get("/")
async def serve_index():
    return FileResponse(str(ROOT_DIR / "index.html"))

@app.get("/chat")
async def serve_chat():
    return FileResponse(str(ROOT_DIR / "chat.html"))

@app.get("/timeline")
async def serve_timeline():
    return FileResponse(str(ROOT_DIR / "timeline.html"))

@app.get("/alternatives")
async def serve_alternatives():
    return FileResponse(str(ROOT_DIR / "alternatives.html"))


@app.get("/api/health")
async def health():
    return {
        "status":  "ok",
        "version": "0.2.0",
        "data": {
            "documents_loaded":            bool(getattr(app.state, "documents", {}).get("documents")),
            "working_groups_loaded":       bool(getattr(app.state, "working_groups", {})),
            "standards_guidelines_loaded": bool(getattr(app.state, "standards_guidelines", {})),
            "full_texts_loaded":           len(getattr(app.state, "full_texts", {})),
        },
    }
