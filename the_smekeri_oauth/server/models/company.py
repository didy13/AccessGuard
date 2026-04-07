"""Pydantic schemas for company and provider CRUD."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProviderConfigIn(BaseModel):
    """Credentials submitted when configuring a provider for a company."""
    provider_name: str
    credentials: dict[str, Any]  # plain — will be encrypted on write
    enabled: bool = True


class ProviderConfigOut(BaseModel):
    id: int
    company_id: str
    provider_name: str
    enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleMappingIn(BaseModel):
    role_name: str
    providers: list[str]


class RoleMappingOut(BaseModel):
    id: int
    company_id: str
    role_name: str
    providers: list[str]

    model_config = {"from_attributes": True}


class CompanyIn(BaseModel):
    company_id: str = Field(..., min_length=1, max_length=100)
    company_name: str = Field(..., min_length=1, max_length=200)
    agent_api_key: str = Field(..., min_length=16)
    enabled: bool = True


class CompanyOut(BaseModel):
    id: int
    company_id: str
    company_name: str
    enabled: bool
    created_at: datetime
    providers: list[ProviderConfigOut] = []

    model_config = {"from_attributes": True}
