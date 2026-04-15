"""
Canonical payload schema shared between company agents and the server.
Both sides import from this module to guarantee format compatibility.
"""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def normalize_provider_name(value: str) -> str:
    raw = (value or "").strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    aliases = {
        "microsoft_365": "microsoft",
        "microsoft_365_entra_id": "microsoft",
        "entra_id": "microsoft",
        "azure": "microsoft",
        "google_workspace": "google",
        "zoho_people": "zoho",
        "sap_s_4hana_cloud": "sap_s4hana_cloud",
    }
    return aliases.get(key, key)


class ActionType(str, Enum):
    TERMINATED = "terminated"
    ROLE_CHANGED = "role_changed"
    ADDED = "added"


class ProviderAccessChange(BaseModel):
    """
    One orchestrated action against a SaaS integration.

    ``entitlements`` is an extensible list of dicts interpreted by each
    provider (e.g. ``{"type": "aad_group", "group_id": "..."}``). An empty
    list means provider-default behaviour (e.g. full session revoke, or
    verify-user grant).
    """

    provider: str = Field(..., description="Registered provider name, e.g. microsoft")
    action: Literal["grant", "revoke"]
    entitlements: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Provider-specific access directives",
    )

    @field_validator("provider")
    @classmethod
    def provider_normalized(cls, v: str) -> str:
        return normalize_provider_name(v)


class AgentPayload(BaseModel):
    """Payload sent by a company agent to the server when an employee event occurs."""

    company_id: str = Field(..., description="Unique company identifier configured on the agent")
    company_name: str = Field(..., description="Human-readable company name")
    employee_email: str = Field(..., description="Employee's corporate email address")
    employee_name: str
    action_type: ActionType
    previous_role: str | None = Field(None, description="Role before change (role_changed only)")
    new_role: str | None = Field(None, description="New role after change; None on termination")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_id: str | None = Field(
        default=None,
        description="Optional idempotency / correlation id (UUID recommended)",
    )

    access_changes: list[ProviderAccessChange] = Field(
        default_factory=list,
        description=(
            "Preferred: ordered list of grant/revoke actions with optional entitlements "
            "per SaaS tool. When empty, saas_revoke / saas_grant are used."
        ),
    )

    saas_revoke: list[str] = Field(
        default_factory=list,
        description="Legacy: provider names whose access must be revoked",
    )
    saas_grant: list[str] = Field(
        default_factory=list,
        description="Legacy: provider names to which access must be granted",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra context")

    @field_validator("employee_email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower().strip()

    @model_validator(mode="after")
    def populate_access_changes_from_legacy(self):
        if self.access_changes:
            return self
        merged: list[ProviderAccessChange] = []
        for p in self.saas_revoke:
            merged.append(
                ProviderAccessChange(provider=p, action="revoke", entitlements=[]),
            )
        for p in self.saas_grant:
            merged.append(
                ProviderAccessChange(provider=p, action="grant", entitlements=[]),
            )
        self.access_changes = merged
        return self

    model_config = {"json_schema_extra": {
        "example": {
            "company_id": "acme-corp",
            "company_name": "Acme Corp",
            "employee_email": "john.doe@acme.com",
            "employee_name": "John Doe",
            "action_type": "terminated",
            "previous_role": "Software Engineer",
            "new_role": None,
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "access_changes": [
                {
                    "provider": "microsoft",
                    "action": "revoke",
                    "entitlements": [],
                },
            ],
            "saas_revoke": [],
            "saas_grant": [],
            "metadata": {"frappe_employee_id": "EMP-0042"},
        }
    }}


class ProviderResult(BaseModel):
    """Result of a single provider action (revoke or grant)."""

    provider: str
    action: str  # "revoke" | "grant"
    success: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(BaseModel):
    """Full result returned by the server after processing a payload."""

    company_id: str
    employee_email: str
    action_type: ActionType
    results: list[ProviderResult]
    processed_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def all_succeeded(self) -> bool:
        return all(r.success for r in self.results)
