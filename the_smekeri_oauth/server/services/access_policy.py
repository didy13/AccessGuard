"""
Server-side access policy: only providers explicitly enabled for a company
may be targeted by incoming events (defense in depth vs. agent misconfig).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from server.database.models import CompanyProvider
from shared.schema import AgentPayload, ProviderAccessChange, ProviderResult


def enabled_provider_names(company_id: str, db: Session) -> set[str]:
    rows = (
        db.query(CompanyProvider.provider_name)
        .filter_by(company_id=company_id, enabled=True)
        .all()
    )
    return {r[0].lower() for r in rows}


def filter_access_changes(
    payload: AgentPayload,
    db: Session,
) -> tuple[list[ProviderAccessChange], list[ProviderResult]]:
    """
    Drop changes for providers that are not enabled for this company.
    Returns (allowed_changes, audit_results_for_skipped).
    """
    allowed = enabled_provider_names(payload.company_id, db)
    kept: list[ProviderAccessChange] = []
    skipped: list[ProviderResult] = []

    for change in payload.access_changes:
        key = change.provider.lower()
        if key in allowed:
            kept.append(change)
            continue
        skipped.append(
            ProviderResult(
                provider=change.provider,
                action=change.action,
                success=False,
                message=(
                    f"Provider '{change.provider}' is not enabled for company "
                    f"'{payload.company_id}' — configure it via admin API or remove "
                    "it from the payload."
                ),
                details={"policy": "provider_not_enabled"},
            )
        )
    return kept, skipped
