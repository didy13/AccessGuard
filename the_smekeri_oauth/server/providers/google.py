"""
Google Workspace provider.

Expected credentials dict keys:
    service_account_info    dict — the parsed content of the service account JSON key file
    admin_email             str  — impersonated admin email (domain-wide delegation)

Entitlements (optional):

    {"type": "workspace_group", "email": "group@yourdomain.com"}

- ``grant`` adds the user as a member of that Google Group.
- ``revoke`` removes the user from that group.

When ``entitlements`` is empty, ``revoke`` revokes OAuth tokens (legacy).
``grant`` verifies the user exists.

Domain-wide delegation must include:
    https://www.googleapis.com/auth/admin.directory.user.readonly
    https://www.googleapis.com/auth/admin.directory.user.security
    https://www.googleapis.com/auth/admin.directory.group.member
"""
from __future__ import annotations

import logging
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.security",
    "https://www.googleapis.com/auth/admin.directory.group.member",
]


class GoogleProvider(BaseProvider):
    name = "google"

    def _build_service(self, credentials: dict) -> Any:
        svc_info: dict = credentials["service_account_info"]
        admin_email: str = credentials["admin_email"]

        creds = service_account.Credentials.from_service_account_info(svc_info, scopes=SCOPES)
        delegated = creds.with_subject(admin_email)
        return build("admin", "directory_v1", credentials=delegated)

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        ents = entitlements or []
        group_ops = [e for e in ents if e.get("type") == "workspace_group" and e.get("email")]
        if ents and not group_ops:
            return ProviderResult(
                "google", "revoke", False,
                "Non-empty entitlements contained no recognized Google directives "
                "(expected type 'workspace_group' with email).",
                details={"entitlements": ents},
            )

        if group_ops:
            try:
                service = self._build_service(credentials)
                errors = []
                for item in group_ops:
                    group_key = str(item["email"])
                    try:
                        service.members().delete(
                            groupKey=group_key,
                            memberKey=email,
                        ).execute()
                    except HttpError as exc:
                        if exc.resp.status == 404:
                            continue
                        errors.append(f"{group_key}: {exc}")
                if errors:
                    return ProviderResult(
                        "google", "revoke", False, "; ".join(errors),
                        details={"entitlements": ents},
                    )
                return ProviderResult(
                    "google", "revoke", True,
                    f"Removed {email} from {len(group_ops)} Google Group(s)",
                    details={"entitlements": ents},
                )
            except HttpError as exc:
                return ProviderResult("google", "revoke", False, f"Google API error: {exc}")
            except Exception as exc:
                return ProviderResult("google", "revoke", False, str(exc))

        try:
            service = self._build_service(credentials)
            result = service.tokens().list(userKey=email).execute()
            tokens = result.get("items", [])

            if not tokens:
                return ProviderResult("google", "revoke", True, f"No active tokens for {email}")

            errors: list[str] = []
            for token in tokens:
                client_id = token.get("clientId")
                if not client_id:
                    continue
                try:
                    service.tokens().delete(userKey=email, clientId=client_id).execute()
                except HttpError as exc:
                    errors.append(f"delete {client_id}: {exc}")

            if errors:
                return ProviderResult("google", "revoke", False, "; ".join(errors))
            return ProviderResult(
                "google", "revoke", True,
                f"Revoked {len(tokens)} token(s) for {email}",
                {"token_count": len(tokens)},
            )

        except HttpError as exc:
            if exc.resp.status == 404:
                return ProviderResult(
                    "google", "revoke", True,
                    f"User {email} not found in Google Workspace — account already removed",
                )
            msg = f"Google API error for {email}: {exc}"
            if exc.resp.status == 403:
                msg += " — check domain-wide delegation scopes"
            logger.error(msg)
            return ProviderResult("google", "revoke", False, msg)
        except Exception as exc:
            logger.error("Unexpected Google error for %s: %s", email, exc)
            return ProviderResult("google", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        ents = entitlements or []
        group_ops = [e for e in ents if e.get("type") == "workspace_group" and e.get("email")]
        if ents and not group_ops:
            return ProviderResult(
                "google", "grant", False,
                "Non-empty entitlements contained no recognized Google directives "
                "(expected type 'workspace_group' with email).",
                details={"entitlements": ents},
            )

        if group_ops:
            try:
                service = self._build_service(credentials)
                errors = []
                for item in group_ops:
                    group_key = str(item["email"])
                    try:
                        service.members().insert(
                            groupKey=group_key,
                            body={"email": email, "role": "MEMBER"},
                        ).execute()
                    except HttpError as exc:
                        if exc.resp.status == 409:
                            continue
                        errors.append(f"{group_key}: {exc}")
                if errors:
                    return ProviderResult(
                        "google", "grant", False, "; ".join(errors),
                        details={"entitlements": ents},
                    )
                return ProviderResult(
                    "google", "grant", True,
                    f"Added {email} to {len(group_ops)} Google Group(s) for role '{role}'",
                    details={"entitlements": ents},
                )
            except HttpError as exc:
                return ProviderResult("google", "grant", False, f"Google API error: {exc}")
            except Exception as exc:
                return ProviderResult("google", "grant", False, str(exc))

        try:
            service = self._build_service(credentials)
            user = service.users().get(userKey=email).execute()
            return ProviderResult(
                "google", "grant", True,
                f"User {email} confirmed in Google Workspace for role '{role}'",
                {"google_id": user.get("id")},
            )
        except HttpError as exc:
            return ProviderResult("google", "grant", False, f"Google API error: {exc}")
        except Exception as exc:
            return ProviderResult("google", "grant", False, str(exc))
