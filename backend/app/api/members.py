"""
Member States API — serve the ISA member state positions tracker data.
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router = APIRouter()

_DATA_DIR: Optional[Path] = None


def load_member_states(data_dir: Path):
    global _DATA_DIR
    _DATA_DIR = data_dir


def _get_data() -> dict:
    if _DATA_DIR is None:
        raise HTTPException(status_code=503, detail="Data not loaded yet")
    path = _DATA_DIR / "member_states.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="member_states.json not found")
    with open(path) as f:
        return json.load(f)


@router.get("/")
async def get_member_states(
    stance: Optional[str] = Query(None, description="Filter by DSM stance: oppose|support|conditional|unknown"),
    region: Optional[str] = Query(None, description="Filter by region"),
    sponsoring: Optional[bool] = Query(None, description="Filter sponsoring states only"),
    green: Optional[bool] = Query(None, description="Filter green governments only"),
    land_mining: Optional[bool] = Query(None, description="Filter land-based mining states only"),
):
    data = _get_data()
    states = data.get("member_states", [])

    if stance:
        states = [s for s in states if s["dsm_position"]["stance"] == stance]
    if region:
        states = [s for s in states if s["region"].lower() == region.lower()]
    if sponsoring is not None:
        states = [s for s in states if s["context"]["sponsoring_state"] == sponsoring]
    if green is not None:
        states = [s for s in states if s["context"]["green_government"] == green]
    if land_mining is not None:
        states = [s for s in states if s["context"]["land_based_mining"] == land_mining]

    return {
        "total": len(states),
        "version": data.get("version"),
        "last_updated": data.get("last_updated"),
        "member_states": states,
    }


@router.get("/summary")
async def get_summary():
    data = _get_data()
    states = data.get("member_states", [])

    stance_counts = {}
    for s in states:
        stance = s["dsm_position"]["stance"]
        stance_counts[stance] = stance_counts.get(stance, 0) + 1

    region_counts = {}
    for s in states:
        region = s["region"]
        region_counts[region] = region_counts.get(region, 0) + 1

    sponsoring = [s["name"] for s in states if s["context"]["sponsoring_state"]]
    land_mining = [s["name"] for s in states if s["context"]["land_based_mining"]]
    green = [s["name"] for s in states if s["context"]["green_government"]]

    return {
        "total_member_states": len(states),
        "last_updated": data.get("last_updated"),
        "by_stance": stance_counts,
        "by_region": region_counts,
        "sponsoring_states": {"count": len(sponsoring), "names": sponsoring},
        "land_based_mining": {"count": len(land_mining), "names": land_mining},
        "green_governments": {"count": len(green), "names": green},
    }


@router.get("/{state_id}")
async def get_member_state(state_id: str):
    data = _get_data()
    for s in data.get("member_states", []):
        if s["id"] == state_id:
            return s
    raise HTTPException(status_code=404, detail=f"Member state '{state_id}' not found")
