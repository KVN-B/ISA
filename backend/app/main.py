"""
ISA Exploitation Regulations App — FastAPI Backend
International Seabed Authority · Polymetallic Nodules
"""

import json
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import documents, chat, regulations

DATA_DIR = Path(__file__).parent.parent.parent / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load documents catalogue into app state."""
    docs_path = DATA_DIR / "documents.json"
    if docs_path.exists():
        with open(docs_path) as f:
            app.state.documents = json.load(f)
        print(f"Loaded {len(app.state.documents['documents'])} documents from catalogue.")
    else:
        app.state.documents = {"documents": []}
        print("WARNING: documents.json not found.")
    yield


app = FastAPI(
    title="ISA Exploitation Regulations API",
    description="API for the International Seabed Authority draft exploitation regulations platform.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(regulations.router, prefix="/api/regulations", tags=["Regulations"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
