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
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from server.admin.routes import router as admin_router
from server.config import get_config
from server.database.db import create_all_tables, get_db
from server.database.models import AuditLog, Company, RoleMapping
from server.models.log import AuditLogOut, LogStatsOut
from server.models.payload import AgentPayload, EventResponse
from server.services.credential_service import company_exists, verify_agent_api_key
from server.services.log_service import get_logs, get_stats
from server.services.router import process_payload
from shared.schema import ActionType, ProviderAccessChange

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
    action_type: str | None = Query(None),
    provider: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return get_logs(
        db,
        company_id=company_id,
        employee_email=employee_email,
        action_type=action_type,
        provider=provider,
        limit=limit,
        offset=offset,
    )


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
# Manual employee actions (admin-only)
# ---------------------------------------------------------------------------

class ManualActionIn(BaseModel):
    action_type: ActionType
    employee_name: str = ""
    previous_role: str | None = None
    new_role: str | None = None


@app.post(
    "/api/v1/companies/{company_id}/employees/{email}/action",
    response_model=EventResponse,
    summary="Manually trigger grant/revoke for an employee (admin only)",
)
def manual_employee_action(
    company_id: str,
    email: str,
    body: ManualActionIn,
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
    db: Session = Depends(get_db),
):
    cfg = get_config()
    if cfg.admin_api_key and x_admin_key != cfg.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    company = db.query(Company).filter_by(company_id=company_id).first()
    if not company:
        raise HTTPException(404, f"Company '{company_id}' not found")

    last_log = (
        db.query(AuditLog)
        .filter_by(company_id=company_id, employee_email=email)
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    employee_name = body.employee_name or (last_log.employee_name if last_log else email)

    access_changes: list[ProviderAccessChange] = []

    if body.action_type == ActionType.TERMINATED:
        if body.previous_role:
            access_changes = _changes_for_role(company_id, body.previous_role, "revoke", db)
        else:
            active = _current_access_providers(email, company_id, db)
            access_changes = [ProviderAccessChange(provider=p, action="revoke", entitlements=[]) for p in active]

    elif body.action_type == ActionType.ROLE_CHANGED:
        revokes = _changes_for_role(company_id, body.previous_role, "revoke", db) if body.previous_role else []
        grants = _changes_for_role(company_id, body.new_role, "grant", db) if body.new_role else []
        access_changes = revokes + grants

    elif body.action_type == ActionType.ADDED:
        access_changes = _changes_for_role(company_id, body.new_role, "grant", db) if body.new_role else []

    if not access_changes:
        raise HTTPException(
            400,
            "No access changes to process — configure role mappings for this company first, "
            "or for 'terminated' the employee must have active access in the audit log.",
        )

    payload = AgentPayload(
        company_id=company_id,
        company_name=company.company_name,
        employee_email=email,
        employee_name=employee_name,
        action_type=body.action_type,
        previous_role=body.previous_role,
        new_role=body.new_role,
        access_changes=access_changes,
        metadata={"triggered_by": "manual"},
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


def _changes_for_role(
    company_id: str, role_name: str | None, action: str, db: Session
) -> list[ProviderAccessChange]:
    if not role_name:
        return []
    rm = db.query(RoleMapping).filter_by(company_id=company_id, role_name=role_name).first()
    if not rm:
        return []
    ents_map = rm.entitlements
    return [
        ProviderAccessChange(
            provider=p,
            action=action,
            entitlements=ents_map.get(p, {}).get(action, []),
        )
        for p in rm.providers
    ]


def _current_access_providers(email: str, company_id: str, db: Session) -> list[str]:
    subq = (
        db.query(AuditLog.provider, func.max(AuditLog.id).label("max_id"))
        .filter(AuditLog.employee_email == email, AuditLog.company_id == company_id)
        .group_by(AuditLog.provider)
        .subquery()
    )
    rows = db.query(AuditLog).join(subq, AuditLog.id == subq.c.max_id).all()
    return [r.provider for r in rows if r.action == "grant" and r.success]


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
    return HTMLResponse(content=html_path.read_text(encoding='utf-8'))
