"""
Alternatives & Preferences API — ISA Member State voting on regulatory alternatives.

Endpoints:
  POST /api/auth/login        — PIN-based login, returns session token
  POST /api/auth/logout       — invalidate token
  GET  /api/auth/me           — validate token, return state info
  GET  /api/alternatives      — return all parsed alternatives (public)
  GET  /api/preferences       — return all votes (public, full transparency)
  POST /api/preferences/{id}  — submit/update a vote (authenticated)
  DELETE /api/preferences/{id} — withdraw a vote (authenticated)
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
PREFS_FILE  = DATA_DIR / "preferences.json"
STATES_FILE = DATA_DIR / "member_states.json"

# In-memory session store: token → {state_code, state_name, is_admin, expires}
_sessions: dict[str, dict] = {}
SESSION_TTL_HOURS = 24


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.strip().encode()).hexdigest()


def _load_states() -> list[dict]:
    if STATES_FILE.exists():
        return json.loads(STATES_FILE.read_text(encoding="utf-8"))
    return []


def _load_prefs() -> dict:
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_prefs(prefs: dict):
    PREFS_FILE.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")


def _validate_token(token: str) -> Optional[dict]:
    session = _sessions.get(token)
    if not session:
        return None
    if datetime.utcnow() > session["expires"]:
        del _sessions[token]
        return None
    return session


def _require_auth(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    session = _validate_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated or session expired.")
    return session


# ── Pydantic models ───────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    state_code: str
    pin: str

class VoteRequest(BaseModel):
    option_index: int   # 0-based index into alternatives[id].options[]
    note: Optional[str] = None   # optional comment


# ── Auth endpoints ────────────────────────────────────────────────────────────

@router.get("/auth/states")
async def list_states():
    """Return all state codes and names (no PINs) for the login dropdown."""
    states = _load_states()
    return [{"code": s["code"], "name": s["name"]} for s in states]


@router.post("/auth/login")
async def login(body: LoginRequest):
    states = _load_states()
    code   = body.state_code.strip().upper()
    hashed = _hash_pin(body.pin)

    state = next(
        (s for s in states if s["code"].upper() == code and s["pin_hash"] == hashed),
        None
    )
    if not state:
        raise HTTPException(status_code=401, detail="Invalid state code or PIN.")

    token = str(uuid.uuid4())
    _sessions[token] = {
        "state_code": state["code"],
        "state_name": state["name"],
        "is_admin":   state.get("is_admin", False),
        "expires":    datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
    }
    return {
        "token":      token,
        "state_code": state["code"],
        "state_name": state["name"],
        "is_admin":   state.get("is_admin", False),
    }


@router.post("/auth/logout")
async def logout(request: Request):
    auth  = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    _sessions.pop(token, None)
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request):
    session = _require_auth(request)
    return {
        "state_code": session["state_code"],
        "state_name": session["state_name"],
        "is_admin":   session["is_admin"],
    }


# ── Alternatives endpoint ─────────────────────────────────────────────────────

@router.get("/alternatives")
async def get_alternatives(request: Request):
    alts_data = getattr(request.app.state, "alternatives", {})
    return alts_data


# ── Preferences endpoints ─────────────────────────────────────────────────────

@router.get("/preferences")
async def get_preferences():
    return _load_prefs()


@router.post("/preferences/{alt_id}")
async def vote(alt_id: str, body: VoteRequest, request: Request):
    session = _require_auth(request)

    # Validate alt_id
    alts_data = getattr(request.app.state, "alternatives", {})
    alts      = alts_data.get("alternatives", [])
    alt       = next((a for a in alts if a["id"] == alt_id), None)
    if not alt:
        raise HTTPException(status_code=404, detail=f"Alternative '{alt_id}' not found.")

    n_options = len(alt.get("options", []))
    if body.option_index < 0 or body.option_index >= n_options:
        raise HTTPException(
            status_code=400,
            detail=f"option_index must be 0–{n_options - 1}."
        )

    prefs = _load_prefs()
    if alt_id not in prefs:
        prefs[alt_id] = {}

    prefs[alt_id][session["state_code"]] = {
        "state_name":   session["state_name"],
        "option_index": body.option_index,
        "option_label": alt["options"][body.option_index]["label"],
        "note":         body.note or "",
        "voted_at":     datetime.utcnow().isoformat() + "Z",
    }
    _save_prefs(prefs)

    return {
        "ok":          True,
        "alt_id":      alt_id,
        "state_code":  session["state_code"],
        "option_index": body.option_index,
    }


@router.delete("/preferences/{alt_id}")
async def withdraw_vote(alt_id: str, request: Request):
    session = _require_auth(request)
    prefs   = _load_prefs()
    if alt_id in prefs and session["state_code"] in prefs[alt_id]:
        del prefs[alt_id][session["state_code"]]
        if not prefs[alt_id]:
            del prefs[alt_id]
        _save_prefs(prefs)
    return {"ok": True, "alt_id": alt_id}
