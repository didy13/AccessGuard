"""
Canonical payload schema shared between company agents and the server.
Both sides import from this module to guarantee format compatibility.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ActionType(str, Enum):
    TERMINATED = "terminated"
    ROLE_CHANGED = "role_changed"
    ADDED = "added"


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
    saas_revoke: list[str] = Field(
        default_factory=list,
        description="Provider names whose access must be revoked (e.g. ['microsoft', 'google'])",
    )
    saas_grant: list[str] = Field(
        default_factory=list,
        description="Provider names to which access must be granted",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra context")

    @field_validator("employee_email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower().strip()

    model_config = {"json_schema_extra": {
        "example": {
            "company_id": "acme-corp",
            "company_name": "Acme Corp",
            "employee_email": "john.doe@acme.com",
            "employee_name": "John Doe",
            "action_type": "terminated",
            "previous_role": "Software Engineer",
            "new_role": None,
            "saas_revoke": ["microsoft", "google"],
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
