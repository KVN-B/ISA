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

from app.api import chat, documents, regulations

DATA_DIR = Path(__file__).parent.parent.parent / "data"


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
    allow_origins=["*"],        # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router,   prefix="/api/documents",   tags=["Documents"])
app.include_router(chat.router,        prefix="/api/chat",        tags=["Chat"])
app.include_router(regulations.router, prefix="/api/regulations", tags=["Regulations"])


@app.get("/api/health")
async def health():
    return {
        "status":  "ok",
        "version": "0.2.0",
        "data": {
            "documents_loaded":          bool(getattr(app.state, "documents", {}).get("documents")),
            "working_groups_loaded":     bool(getattr(app.state, "working_groups", {})),
            "standards_guidelines_loaded": bool(getattr(app.state, "standards_guidelines", {})),
        },
    }
