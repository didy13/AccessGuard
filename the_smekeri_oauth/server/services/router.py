"""
Execution router.

Receives a validated AgentPayload, calls the appropriate provider scripts,
records every result in the audit log, and returns an ExecutionReport.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from server.providers.registry import get_provider
from server.services.access_policy import filter_access_changes
from server.services.credential_service import get_credentials
from server.services.log_service import record_result
from shared.schema import AgentPayload, ExecutionReport, ProviderAccessChange, ProviderResult

logger = logging.getLogger(__name__)


def process_payload(payload: AgentPayload, db: Session) -> ExecutionReport:
    results: list[ProviderResult] = []

    allowed_changes, policy_skips = filter_access_changes(payload, db)
    for pr in policy_skips:
        record_result(payload, pr, db)
        results.append(pr)

    ordered = sorted(
        allowed_changes,
        key=lambda c: (0 if c.action == "revoke" else 1, c.provider.lower()),
    )

    for change in ordered:
        result = _run_provider(change, payload, db)
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
    change: ProviderAccessChange,
    payload: AgentPayload,
    db: Session,
) -> ProviderResult:
    provider_name = change.provider
    action = change.action
    entitlements = change.entitlements

    try:
        provider = get_provider(provider_name)
    except ValueError as exc:
        result = ProviderResult(
            provider=provider_name, action=action,
            success=False, message=str(exc),
            details={"entitlements": entitlements},
        )
        record_result(payload, result, db)
        return result

    credentials = get_credentials(payload.company_id, provider_name, db)
    if credentials is None:
        result = ProviderResult(
            provider=provider_name, action=action,
            success=False,
            message=(
                f"No credentials configured for provider '{provider_name}' "
                f"on company '{payload.company_id}'"
            ),
            details={"entitlements": entitlements},
        )
        record_result(payload, result, db)
        return result

    try:
        if action == "revoke":
            result = provider.revoke(payload.employee_email, credentials, entitlements)
        else:
            result = provider.grant(
                payload.employee_email,
                payload.new_role or "",
                credentials,
                entitlements,
            )
    except Exception as exc:
        logger.exception("Unhandled error in provider %s", provider_name)
        result = ProviderResult(
            provider=provider_name, action=action,
            success=False, message=f"Unhandled exception: {exc}",
            details={"entitlements": entitlements},
        )

    logger.info(
        "[%s] %s.%s(%s) → %s",
        payload.company_id, provider_name, action,
        payload.employee_email,
        "OK" if result.success else f"FAIL: {result.message}",
    )
    record_result(payload, result, db)
    return result
