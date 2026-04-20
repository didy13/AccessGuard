"""SQLAlchemy ORM models."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_api_key: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    providers: Mapped[list[CompanyProvider]] = relationship(
        "CompanyProvider", back_populates="company", cascade="all, delete-orphan"
    )
    role_mappings: Mapped[list[RoleMapping]] = relationship(
        "RoleMapping", back_populates="company", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="company", cascade="all, delete-orphan"
    )


class CompanyProvider(Base):
    """Stores encrypted API credentials for one provider of one company."""

    __tablename__ = "company_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("companies.company_id"), nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)  # "microsoft" | "google"
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Company] = relationship("Company", back_populates="providers")


class RoleMapping(Base):
    """Maps a job title to the list of SaaS providers for a company."""

    __tablename__ = "role_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("companies.company_id"), nullable=False
    )
    role_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # JSON array of provider names, e.g. '["microsoft","google"]'
    providers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # JSON dict: provider -> {grant: [...], revoke: [...]} entitlements
    entitlements_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    company: Mapped[Company] = relationship("Company", back_populates="role_mappings")

    @property
    def providers(self) -> list[str]:
        return json.loads(self.providers_json)

    @providers.setter
    def providers(self, value: list[str]) -> None:
        self.providers_json = json.dumps(value)

    @property
    def entitlements(self) -> dict:
        return json.loads(self.entitlements_json)

    @entitlements.setter
    def entitlements(self, value: dict) -> None:
        self.entitlements_json = json.dumps(value)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("companies.company_id"), nullable=False, index=True
    )
    employee_email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)   # terminated|role_changed|added
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)         # revoke|grant
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    company: Mapped[Company] = relationship("Company", back_populates="audit_logs")
