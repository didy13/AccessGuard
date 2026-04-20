"""
Local dashboard served by the agent on localhost.

Exposes:
  GET  /                           — HTML dashboard
  GET  /api/status                 — full state snapshot (JSON)
  GET  /api/stream                 — SSE stream: countdown + last scan summary (1s ticks)
  GET  /api/employees              — current employee snapshot from state file
  GET  /api/role-mappings          — UI-configured role → provider mappings
  PUT  /api/role-mappings/{role}   — upsert a role mapping
  DELETE /api/role-mappings/{role} — delete a role mapping
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from .dashboard_state import state
from .state import load_state

app = FastAPI(title="AccessGuard Agent", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Helpers for UI role mappings persistence
# ---------------------------------------------------------------------------

def _mappings_path() -> Path:
    return Path(state.ui_mappings_file)


def _load_ui_mappings() -> dict[str, list[str]]:
    p = _mappings_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data.get("role_provider_map", {})
    except Exception:
        return {}


def _save_ui_mappings(mappings: dict[str, list[str]]) -> None:
    _mappings_path().write_text(json.dumps({"role_provider_map": mappings}, indent=2))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    html = (Path(__file__).parent / "dashboard_ui.html").read_text()
    return HTMLResponse(html)


@app.get("/api/status")
def api_status():
    return state.snapshot()


@app.get("/api/employees")
def api_employees():
    """Return current employee list from the persisted state file."""
    snapshot = load_state(state.state_file)
    return [
        {"email": email, "name": data["name"], "role": data["role"], "status": data["status"]}
        for email, data in sorted(snapshot.items(), key=lambda x: x[1].get("name", ""))
    ]


@app.get("/api/role-mappings")
def api_get_role_mappings():
    """Return UI-configured role → provider mappings."""
    mappings = _load_ui_mappings()
    return [
        {"role": role, "providers": providers}
        for role, providers in sorted(mappings.items())
    ]


@app.put("/api/role-mappings/{role}")
async def api_upsert_role_mapping(role: str, request: Request):
    """Create or update a role → provider mapping."""
    body: dict[str, Any] = await request.json()
    providers = body.get("providers", [])
    if not isinstance(providers, list) or not all(isinstance(p, str) for p in providers):
        raise HTTPException(400, "providers must be a list of strings")
    mappings = _load_ui_mappings()
    mappings[role] = [p.strip() for p in providers if p.strip()]
    _save_ui_mappings(mappings)
    return {"role": role, "providers": mappings[role]}


@app.delete("/api/role-mappings/{role}", status_code=204)
def api_delete_role_mapping(role: str):
    """Remove a role mapping."""
    mappings = _load_ui_mappings()
    if role not in mappings:
        raise HTTPException(404, f"Role '{role}' not found")
    del mappings[role]
    _save_ui_mappings(mappings)


@app.get("/api/stream")
async def api_stream():
    """SSE stream — sends a tick every second with countdown info."""

    async def generator():
        while True:
            snap = state.snapshot()
            seconds_left: int | None = None
            if snap["next_scan"]:
                next_dt = datetime.fromisoformat(snap["next_scan"])
                now = datetime.utcnow()
                seconds_left = max(0, int((next_dt - now).total_seconds()))

            last = snap["scan_history"][0] if snap["scan_history"] else None
            tick = {
                "seconds_left": seconds_left,
                "poll_interval": snap["poll_interval"],
                "last_scan": snap["last_scan"],
                "last_changes_count": last["changes_count"] if last else 0,
                "last_all_succeeded": last["all_succeeded"] if last else True,
            }
            yield f"data: {json.dumps(tick)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run(host: str, port: int) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


def start_dashboard_thread(host: str = "127.0.0.1", port: int = 7979) -> None:
    t = threading.Thread(target=_run, args=(host, port), daemon=True)
    t.start()
