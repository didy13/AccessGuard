"""Create and query audit log entries."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from server.database.models import AuditLog
from server.providers.base import ProviderResult
from shared.schema import AgentPayload


def record_result(payload: AgentPayload, result: ProviderResult, db: Session) -> AuditLog:
    details = dict(result.details)
    if payload.event_id:
        details["event_id"] = payload.event_id

    entry = AuditLog(
        company_id=payload.company_id,
        employee_email=payload.employee_email,
        employee_name=payload.employee_name,
        action_type=payload.action_type.value,
        provider=result.provider,
        action=result.action,
        success=result.success,
        message=result.message,
        details_json=json.dumps(details),
        timestamp=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_logs(
    db: Session,
    company_id: str | None = None,
    employee_email: str | None = None,
    action_type: str | None = None,
    provider: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if company_id:
        q = q.filter(AuditLog.company_id == company_id)
    if employee_email:
        q = q.filter(AuditLog.employee_email.ilike(f"%{employee_email}%"))
    if action_type:
        q = q.filter(AuditLog.action_type == action_type)
    if provider:
        q = q.filter(AuditLog.provider == provider)
    return q.offset(offset).limit(limit).all()


def get_stats(db: Session, company_id: str | None = None) -> dict:
    q = db.query(AuditLog)
    if company_id:
        q = q.filter(AuditLog.company_id == company_id)
    total = q.count()
    succeeded = q.filter(AuditLog.success == True).count()  # noqa: E712
    failed = total - succeeded
    return {"total": total, "succeeded": succeeded, "failed": failed}
