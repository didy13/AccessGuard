"""Request/response schemas for the /api/v1/events endpoint."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from shared.schema import (
    ActionType,
    AgentPayload,
    ExecutionReport,
    ProviderAccessChange,
    ProviderResult,
)

# Re-export for use in routes
__all__ = [
    "AgentPayload",
    "ExecutionReport",
    "ProviderAccessChange",
    "ProviderResult",
    "ActionType",
]


class EventResponse(BaseModel):
    status: str
    company_id: str
    employee_email: str
    action_type: ActionType
    results: list[ProviderResult]
    processed_at: datetime
    all_succeeded: bool
