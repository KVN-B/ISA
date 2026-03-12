# ISA Exploitation Regulations Platform

Open-source platform for the development of exploitation regulations for mineral resources in the Area (polymetallic nodules) — International Seabed Authority.

**Current regulatory text:** `ISBA/31/C/CRP.1/Rev.2` (February 2026)

---

## What this platform does

| Feature | Description |
|---|---|
| **Document Timeline** | Interactive visualisation of all 33 documents from 2014 discussion papers to the current text |
| **Regulation Viewer** | Browse ISBA/31/C/CRP.1/Rev.2 with bracket/alternative/circular highlighting |
| **RAG Chat** | Ask questions grounded strictly in the regulatory text — no hallucination, cites provisions |
| **Status Tracking** | Per-provision status (agreed / bracketed / alternative / suspended) |
| **Multi-language** | All 6 UN official languages (EN, FR, ES, AR, ZH, RU) |
| **Open Source** | Public, same view for all stakeholders |

---

## Quick Start

### 1. View the document timeline immediately
Open `timeline.html` in any browser — no server needed.

### 2. Run the backend (Python 3.9+)

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

### 3. Ingest documents into the vector database

```bash
cd backend
python scripts/ingest_documents.py
```

This downloads and indexes the ISA regulatory texts from `isa.org.jm`.

### 4. Run the frontend (Node.js 18+)

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open `http://localhost:3000`.

---

## Document Corpus

| Document | Reference | Date | Status |
|---|---|---|---|
| Further Revised Consolidated Text | ISBA/31/C/CRP.1/Rev.2 | Feb 2026 | **CURRENT** |
| Further Revised Consolidated Text (clean) | ISBA/31/C/CRP.2/Rev.2 | Feb 2026 | Current |
| Further Revised Suspense Document | ISBA/31/C/CRP.3 | Dec 2025 | Current |
| Outstanding Issues List | ISBA/31/C/CRP.4 | Feb 2026 | Current |
| Revised Consolidated Text | ISBA/30/C/CRP.1 | Nov 2024 | Superseded |
| Consolidated Text | ISBA/29/C/CRP.1 | Feb 2024 | Superseded |
| Draft Regulations | ISBA/25/C/WP.1 | Mar 2019 | Superseded |
| First Working Draft | — | Feb 2016 | Historical |

See `data/documents.json` for the complete catalogue of 33 documents.

---

## Architecture

```
isa-exploitation-regulations/
├── timeline.html          # Standalone interactive timeline (no server needed)
├── data/
│   └── documents.json     # Complete document catalogue (33 documents, 2014–2026)
├── backend/               # FastAPI (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── documents.py    # Document catalogue API
│   │   │   ├── chat.py         # RAG chat (Claude-powered)
│   │   │   └── regulations.py  # Regulation structure + circular detection
│   │   └── services/
│   ├── scripts/
│   │   └── ingest_documents.py # Downloads + indexes ISA PDFs
│   └── requirements.txt
└── frontend/              # Next.js 14 (React, TypeScript, Tailwind)
    └── src/
        ├── app/
        │   ├── page.tsx         # Dashboard
        │   ├── timeline/        # Document timeline
        │   ├── regulations/     # Regulation viewer
        │   └── chat/            # RAG chat interface
        └── components/
```

---

## Environment Variables

| Variable | Where | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | backend `.env` | Required for the chat feature |
| `NEXT_PUBLIC_API_URL` | frontend `.env.local` | Backend URL (default: `http://localhost:8000`) |

---

## Roadmap

- [x] Document catalogue + interactive timeline
- [x] FastAPI backend with document, chat, and regulations APIs
- [x] RAG chat grounded in regulatory texts
- [ ] Provision-level status index (ingest_documents.py → complete)
- [ ] Circular dependency detector
- [ ] Suggestions engine for unresolved brackets
- [ ] Voting / stakeholder signalling
- [ ] Full multi-language support
- [ ] ISA server deployment

---

## Contributing

This is an open-source project. All contributions welcome via pull requests on [GitHub](https://github.com/KVN-B/ISA).

---

## Data Sources

All documents sourced from the International Seabed Authority: [isa.org.jm](https://www.isa.org.jm)
