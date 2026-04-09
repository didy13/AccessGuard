"""
Local dashboard served by the agent on localhost.

Exposes:
  GET /                — HTML dashboard
  GET /api/status      — full state snapshot (JSON)
  GET /api/stream      — SSE stream: countdown + last scan summary (1s ticks)
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from .dashboard_state import state

app = FastAPI(title="AccessGuard Agent", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    html = (Path(__file__).parent / "dashboard_ui.html").read_text()
    return HTMLResponse(html)


@app.get("/api/status")
def api_status():
    return state.snapshot()


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
