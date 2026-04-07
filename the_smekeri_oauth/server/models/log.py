"""Pydantic schemas for audit log queries and responses."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator


class AuditLogOut(BaseModel):
    id: int
    company_id: str
    employee_email: str
    employee_name: str
    action_type: str
    provider: str
    action: str
    success: bool
    message: str
    details: dict[str, Any] = {}
    timestamp: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def parse_details_json(cls, values):
        # ORM object has details_json; we expose it as `details`
        if hasattr(values, "details_json"):
            try:
                object.__setattr__(values, "details", json.loads(values.details_json))
            except Exception:
                pass
        return values


class LogStatsOut(BaseModel):
    total: int
    succeeded: int
    failed: int
