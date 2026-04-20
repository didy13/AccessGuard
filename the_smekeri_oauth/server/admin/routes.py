"""
Admin panel API routes.

All routes require the X-Admin-Key header matching ADMIN_API_KEY.
Clients (dashboard) call these to manage companies, providers, and role mappings.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from server.config import get_config
from server.database.db import get_db
from server.database.models import Company, CompanyProvider, RoleMapping
from server.models.company import (
    CompanyIn, CompanyOut,
    ProviderConfigIn, ProviderConfigOut,
    RoleMappingIn, RoleMappingOut,
)
from server.providers.registry import list_providers
from server.services.credential_service import encrypt_credentials
from shared.schema import normalize_provider_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_admin(x_admin_key: str = Header(...)):
    if get_config().admin_api_key and x_admin_key != get_config().admin_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

@router.get("/companies", response_model=list[CompanyOut], dependencies=[Depends(require_admin)])
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()


@router.post("/companies", response_model=CompanyOut, status_code=201, dependencies=[Depends(require_admin)])
def create_company(body: CompanyIn, db: Session = Depends(get_db)):
    if db.query(Company).filter_by(company_id=body.company_id).first():
        raise HTTPException(400, f"Company '{body.company_id}' already exists")
    company = Company(**body.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.patch("/companies/{company_id}", response_model=CompanyOut, dependencies=[Depends(require_admin)])
def update_company(company_id: str, body: CompanyIn, db: Session = Depends(get_db)):
    company = _get_company_or_404(company_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company


@router.delete("/companies/{company_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_company(company_id: str, db: Session = Depends(get_db)):
    company = _get_company_or_404(company_id, db)
    db.delete(company)
    db.commit()


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@router.get("/companies/{company_id}/providers", response_model=list[ProviderConfigOut], dependencies=[Depends(require_admin)])
def list_company_providers(company_id: str, db: Session = Depends(get_db)):
    _get_company_or_404(company_id, db)
    return db.query(CompanyProvider).filter_by(company_id=company_id).all()


@router.put("/companies/{company_id}/providers/{provider_name}", response_model=ProviderConfigOut, dependencies=[Depends(require_admin)])
def upsert_provider(
    company_id: str,
    provider_name: str,
    body: ProviderConfigIn,
    db: Session = Depends(get_db),
):
    _get_company_or_404(company_id, db)
    normalized_name = normalize_provider_name(provider_name)
    if body.provider_name and normalize_provider_name(body.provider_name) != normalized_name:
        raise HTTPException(
            400,
            f"Path provider '{provider_name}' does not match body.provider_name '{body.provider_name}'",
        )
    if normalized_name not in list_providers():
        raise HTTPException(400, f"Unknown provider '{provider_name}'. Available: {list_providers()}")

    row = db.query(CompanyProvider).filter_by(company_id=company_id, provider_name=normalized_name).first()
    if not row:
        row = CompanyProvider(company_id=company_id, provider_name=normalized_name)
        db.add(row)

    try:
        row.credentials_encrypted = encrypt_credentials(body.credentials)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    row.enabled = body.enabled
    db.commit()
    db.refresh(row)
    return row


@router.delete("/companies/{company_id}/providers/{provider_name}", status_code=204, dependencies=[Depends(require_admin)])
def delete_provider(company_id: str, provider_name: str, db: Session = Depends(get_db)):
    normalized_name = normalize_provider_name(provider_name)
    row = db.query(CompanyProvider).filter_by(company_id=company_id, provider_name=normalized_name).first()
    if not row:
        raise HTTPException(404, "Provider not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Role Mappings
# ---------------------------------------------------------------------------

@router.get("/companies/{company_id}/roles", response_model=list[RoleMappingOut], dependencies=[Depends(require_admin)])
def list_role_mappings(company_id: str, db: Session = Depends(get_db)):
    _get_company_or_404(company_id, db)
    rows = db.query(RoleMapping).filter_by(company_id=company_id).all()
    return [
        RoleMappingOut(id=r.id, company_id=r.company_id, role_name=r.role_name, providers=r.providers, entitlements=r.entitlements)
        for r in rows
    ]


@router.put("/companies/{company_id}/roles/{role_name}", response_model=RoleMappingOut, dependencies=[Depends(require_admin)])
def upsert_role_mapping(company_id: str, role_name: str, body: RoleMappingIn, db: Session = Depends(get_db)):
    _get_company_or_404(company_id, db)
    row = db.query(RoleMapping).filter_by(company_id=company_id, role_name=role_name).first()
    if not row:
        row = RoleMapping(company_id=company_id, role_name=role_name)
        db.add(row)
    row.providers = body.providers
    row.entitlements = body.entitlements
    db.commit()
    db.refresh(row)
    return RoleMappingOut(id=row.id, company_id=row.company_id, role_name=row.role_name, providers=row.providers, entitlements=row.entitlements)


@router.delete("/companies/{company_id}/roles/{role_name}", status_code=204, dependencies=[Depends(require_admin)])
def delete_role_mapping(company_id: str, role_name: str, db: Session = Depends(get_db)):
    row = db.query(RoleMapping).filter_by(company_id=company_id, role_name=role_name).first()
    if not row:
        raise HTTPException(404, "Role mapping not found")
    db.delete(row)
    db.commit()


@router.get("/providers", dependencies=[Depends(require_admin)])
def available_providers():
    return {"providers": list_providers()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_company_or_404(company_id: str, db: Session) -> Company:
    company = db.query(Company).filter_by(company_id=company_id).first()
    if not company:
        raise HTTPException(404, f"Company '{company_id}' not found")
    return company
