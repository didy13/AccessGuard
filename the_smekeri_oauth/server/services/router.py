"""
Execution router.

Receives a validated AgentPayload, calls the appropriate provider scripts,
records every result in the audit log, and returns an ExecutionReport.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from server.providers.registry import get_provider
from server.services.credential_service import get_credentials
from server.services.log_service import record_result
from shared.schema import AgentPayload, ExecutionReport, ProviderResult

logger = logging.getLogger(__name__)


def process_payload(payload: AgentPayload, db: Session) -> ExecutionReport:
    results: list[ProviderResult] = []

    # --- REVOKE ---
    for provider_name in payload.saas_revoke:
        result = _run_provider(provider_name, "revoke", payload, db)
        results.append(result)

    # --- GRANT ---
    for provider_name in payload.saas_grant:
        result = _run_provider(provider_name, "grant", payload, db)
        results.append(result)

    if not results:
        logger.info(
            "[%s] No providers to call for %s (%s)",
            payload.company_id, payload.employee_email, payload.action_type,
        )

    return ExecutionReport(
        company_id=payload.company_id,
        employee_email=payload.employee_email,
        action_type=payload.action_type,
        results=results,
    )


def _run_provider(
    provider_name: str,
    action: str,
    payload: AgentPayload,
    db: Session,
) -> ProviderResult:
    try:
        provider = get_provider(provider_name)
    except ValueError as exc:
        result = ProviderResult(
            provider=provider_name, action=action,
            success=False, message=str(exc),
        )
        record_result(payload, result, db)
        return result

    credentials = get_credentials(payload.company_id, provider_name, db)
    if credentials is None:
        result = ProviderResult(
            provider=provider_name, action=action,
            success=False,
            message=f"No credentials configured for provider '{provider_name}' "
                    f"on company '{payload.company_id}'",
        )
        record_result(payload, result, db)
        return result

    try:
        if action == "revoke":
            result = provider.revoke(payload.employee_email, credentials)
        else:
            result = provider.grant(
                payload.employee_email,
                payload.new_role or "",
                credentials,
            )
    except Exception as exc:
        logger.exception("Unhandled error in provider %s", provider_name)
        result = ProviderResult(
            provider=provider_name, action=action,
            success=False, message=f"Unhandled exception: {exc}",
        )

    logger.info(
        "[%s] %s.%s(%s) → %s",
        payload.company_id, provider_name, action,
        payload.employee_email,
        "OK" if result.success else f"FAIL: {result.message}",
    )
    record_result(payload, result, db)
    return result
