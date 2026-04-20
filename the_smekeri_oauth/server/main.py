"""
Server entry point.

Exposes:
  POST /api/v1/events       — receives payloads from company agents
  GET  /api/v1/logs         — query audit logs
  GET  /api/v1/logs/stats   — aggregate stats
  /admin/*                  — admin panel API (requires X-Admin-Key)
  GET  /                    — web dashboard (HTML)
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import func
from sqlalchemy.orm import Session

from server.admin.routes import router as admin_router
from server.config import get_config
from server.database.db import create_all_tables, get_db
from server.database.models import AuditLog
from server.models.log import AuditLogOut, LogStatsOut
from server.models.payload import AgentPayload, EventResponse
from server.services.credential_service import company_exists, verify_agent_api_key
from server.services.log_service import get_logs, get_stats
from server.services.router import process_payload

# Import providers so they register themselves
import server.providers  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("accessguard.server")

app = FastAPI(
    title="AccessGuard",
    description="Automated SaaS access management — receives employee lifecycle events and revokes or grants provider access.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    create_all_tables()
    logger.info("Database tables created / verified")


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_agent_auth(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """Validate agent API key against company record."""
    # The company_id is in the body — we do per-payload check in the route.
    # This dependency just ensures the header is present.
    if get_config().auth_enabled and not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-API-Key header required")
    return x_api_key


# ---------------------------------------------------------------------------
# Event ingestion
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/events",
    response_model=EventResponse,
    status_code=202,
    summary="Receive employee lifecycle event from a company agent",
)
def ingest_event(
    payload: AgentPayload,
    x_api_key: str = Header(default="", alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    cfg = get_config()

    if cfg.auth_enabled:
        if not verify_agent_api_key(payload.company_id, x_api_key, db):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key for this company",
            )

    if not company_exists(payload.company_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{payload.company_id}' not found or disabled",
        )

    logger.info(
        "Event received: company=%s email=%s action=%s",
        payload.company_id, payload.employee_email, payload.action_type,
    )

    report = process_payload(payload, db)

    return EventResponse(
        status="processed",
        company_id=report.company_id,
        employee_email=report.employee_email,
        action_type=report.action_type,
        results=report.results,
        processed_at=report.processed_at,
        all_succeeded=report.all_succeeded,
    )


# ---------------------------------------------------------------------------
# Logs API (used by dashboard)
# ---------------------------------------------------------------------------

@app.get("/api/v1/logs", response_model=list[AuditLogOut])
def query_logs(
    company_id: str | None = Query(None),
    employee_email: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return get_logs(db, company_id=company_id, employee_email=employee_email, limit=limit, offset=offset)


@app.get("/api/v1/logs/stats", response_model=LogStatsOut)
def log_stats(
    company_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return get_stats(db, company_id=company_id)


# ---------------------------------------------------------------------------
# Users API
# ---------------------------------------------------------------------------

@app.get("/api/v1/users")
def list_users(
    company_id: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Return distinct users seen in audit logs, with optional search/filter."""
    subq = (
        db.query(
            AuditLog.employee_email,
            AuditLog.employee_name,
            AuditLog.company_id,
            func.max(AuditLog.timestamp).label("last_seen"),
        )
        .group_by(AuditLog.employee_email, AuditLog.company_id)
    )
    if company_id:
        subq = subq.filter(AuditLog.company_id == company_id)
    if search:
        subq = subq.filter(
            (AuditLog.employee_email.ilike(f"%{search}%"))
            | (AuditLog.employee_name.ilike(f"%{search}%"))
        )
    rows = subq.order_by(func.max(AuditLog.timestamp).desc()).all()
    return [
        {
            "email": r.employee_email,
            "name": r.employee_name,
            "company_id": r.company_id,
            "last_seen": r.last_seen,
        }
        for r in rows
    ]


@app.get("/api/v1/users/{email}/tokens")
def user_tokens(
    email: str,
    company_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Return the most-recent access state per provider for a given user."""
    subq = (
        db.query(AuditLog.provider, func.max(AuditLog.id).label("max_id"))
        .filter(AuditLog.employee_email == email)
    )
    if company_id:
        subq = subq.filter(AuditLog.company_id == company_id)
    subq = subq.group_by(AuditLog.provider).subquery()

    rows = (
        db.query(AuditLog)
        .join(subq, AuditLog.id == subq.c.max_id)
        .order_by(AuditLog.provider)
        .all()
    )
    return [
        {
            "provider": r.provider,
            "action": r.action,
            "success": r.success,
            "has_access": r.action == "grant" and r.success,
            "action_type": r.action_type,
            "timestamp": r.timestamp,
            "message": r.message,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Admin router
# ---------------------------------------------------------------------------

app.include_router(admin_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Dashboard (single-page HTML)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    html_path = Path(__file__).parent / "dashboard" / "index.html"
    return HTMLResponse(content=html_path.read_text())
