"""Encrypt/decrypt provider credentials stored in the database."""
from __future__ import annotations

import json
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from server.config import get_config
from server.database.models import Company, CompanyProvider
from shared.schema import normalize_provider_name

logger = logging.getLogger(__name__)

# Stored when ENCRYPTION_KEY is unset and credentials are {} (e.g. mock providers in local dev).
_EMPTY_CREDENTIALS_PLACEHOLDER = "__accessguard_empty_credentials__"


def _fernet() -> Fernet:
    key = get_config().encryption_key
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_credentials(data: dict) -> str:
    if not data:
        if not get_config().encryption_key.strip():
            return _EMPTY_CREDENTIALS_PLACEHOLDER
        return _fernet().encrypt(json.dumps(data).encode()).decode()
    if not get_config().encryption_key.strip():
        raise RuntimeError(
            "ENCRYPTION_KEY is not set but non-empty provider credentials were submitted. "
            "Set ENCRYPTION_KEY in server/.env or the project root .env, or use empty credentials."
        )
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(encrypted: str) -> dict:
    if not encrypted or encrypted == _EMPTY_CREDENTIALS_PLACEHOLDER:
        return {}
    if not get_config().encryption_key.strip():
        logger.warning(
            "ENCRYPTION_KEY is not set — cannot decrypt stored credentials; treating as empty"
        )
        return {}
    try:
        return json.loads(_fernet().decrypt(encrypted.encode()))
    except InvalidToken:
        logger.error("Failed to decrypt credentials — wrong key or corrupted data")
        return {}


def get_credentials(company_id: str, provider_name: str, db: Session) -> dict | None:
    """
    Load and decrypt credentials for a given company + provider.
    Returns None when no provider row exists (not configured).
    Returns {} when the row exists but credentials are intentionally empty (e.g. mock providers).
    """
    normalized = normalize_provider_name(provider_name)
    candidate_names = {provider_name.lower(), normalized}
    row = (
        db.query(CompanyProvider)
        .filter(CompanyProvider.company_id == company_id)
        .filter(CompanyProvider.enabled.is_(True))
        .filter(CompanyProvider.provider_name.in_(candidate_names))
        .first()
    )
    if not row:
        return None
    return decrypt_credentials(row.credentials_encrypted)


def company_exists(company_id: str, db: Session) -> bool:
    return db.query(Company).filter_by(company_id=company_id, enabled=True).first() is not None


def verify_agent_api_key(company_id: str, api_key: str, db: Session) -> bool:
    company = db.query(Company).filter_by(company_id=company_id).first()
    if not company:
        return False
    return company.agent_api_key == api_key
