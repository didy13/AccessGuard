"""
Groove provider — helpdesk platform for Serbian MSPs (groovehq.com).

Expected credentials dict keys:
    access_token   Groove OAuth2 access token
                   (Groove → Settings → API → Generate Access Token)

Revoke: removes the agent from all mailboxes they belong to, effectively
        revoking their access to all support queues. Groove's v1 API does not
        have a direct agent deactivation endpoint, so mailbox membership removal
        is the canonical access-revocation approach.
Grant:  adds the agent back as a member of the mailboxes listed in entitlements.
        Without entitlements, grant only verifies the agent exists.

Entitlements (optional):
    {"type": "groove_mailbox", "mailbox_id": "<mailbox-id>"}

API docs: https://www.groovehq.com/docs
Base URL:  https://api.groovehq.com/v1/
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

GROOVE_BASE = "https://api.groovehq.com/v1"


class GrooveProvider(BaseProvider):
    name = "groove"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": f"Bearer {credentials['access_token']}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _find_agent(self, email: str, credentials: dict) -> dict | None:
        headers = self._auth_headers(credentials)
        page = 1
        while True:
            try:
                resp = requests.get(
                    f"{GROOVE_BASE}/agents",
                    headers=headers,
                    params={"page": page, "per_page": 50},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                agents = data.get("agents", [])
                if not agents:
                    return None
                for agent in agents:
                    if agent.get("email", "").lower() == email.lower():
                        return agent
                meta = data.get("meta", {})
                pagination = meta.get("pagination", {})
                if page >= pagination.get("total_pages", 1):
                    return None
                page += 1
            except requests.RequestException as exc:
                logger.error("Groove agent lookup error: %s", exc)
                return None

    def _list_mailboxes(self, credentials: dict) -> list[dict]:
        headers = self._auth_headers(credentials)
        try:
            resp = requests.get(f"{GROOVE_BASE}/mailboxes", headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json().get("mailboxes", [])
        except requests.RequestException as exc:
            logger.error("Groove mailbox list error: %s", exc)
            return []

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        agent = self._find_agent(email, credentials)
        if not agent:
            return ProviderResult(
                "groove", "revoke", True,
                f"Groove agent {email} not found — already removed or never added",
            )

        agent_email = agent.get("email", email)
        headers = self._auth_headers(credentials)

        # Determine which mailboxes to remove from
        ents = entitlements or []
        mailbox_ids = [
            e["mailbox_id"]
            for e in ents
            if e.get("type") == "groove_mailbox" and e.get("mailbox_id")
        ]
        if not mailbox_ids:
            # Remove from all mailboxes the agent belongs to
            mailbox_ids = [mb["id"] for mb in self._list_mailboxes(credentials)]

        errors: list[str] = []
        removed = 0
        for mailbox_id in mailbox_ids:
            try:
                resp = requests.delete(
                    f"{GROOVE_BASE}/mailboxes/{mailbox_id}/agents/{agent_email}",
                    headers=headers,
                    timeout=30,
                )
                if resp.status_code in (200, 204, 404):
                    removed += 1
                else:
                    errors.append(f"mailbox {mailbox_id}: {resp.status_code}")
            except requests.RequestException as exc:
                errors.append(f"mailbox {mailbox_id}: {exc}")

        if errors:
            return ProviderResult(
                "groove", "revoke", False,
                f"Groove partial revoke — {removed} mailbox(es) OK, errors: {'; '.join(errors)}",
                {"agent_email": agent_email},
            )
        return ProviderResult(
            "groove", "revoke", True,
            f"Removed Groove agent {email} from {removed} mailbox(es)",
            {"agent_email": agent_email, "mailboxes_removed": removed},
        )

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        agent = self._find_agent(email, credentials)
        if not agent:
            return ProviderResult(
                "groove", "grant", False,
                f"Groove agent {email} not found — invite them to Groove first",
            )

        ents = entitlements or []
        mailbox_ops = [
            e for e in ents
            if e.get("type") == "groove_mailbox" and e.get("mailbox_id")
        ]
        if not mailbox_ops:
            return ProviderResult(
                "groove", "grant", True,
                f"Groove agent {email} exists (role='{role}'). Add 'groove_mailbox' entitlements to assign mailboxes.",
                {"agent_email": agent.get("email")},
            )

        headers = self._auth_headers(credentials)
        errors: list[str] = []
        added = 0
        for item in mailbox_ops:
            mailbox_id = item["mailbox_id"]
            try:
                resp = requests.post(
                    f"{GROOVE_BASE}/mailboxes/{mailbox_id}/agents",
                    headers=headers,
                    json={"email": email},
                    timeout=30,
                )
                if resp.status_code in (200, 201, 204):
                    added += 1
                elif resp.status_code == 422 and "already" in resp.text.lower():
                    added += 1  # already a member
                else:
                    errors.append(f"mailbox {mailbox_id}: {resp.status_code}")
            except requests.RequestException as exc:
                errors.append(f"mailbox {mailbox_id}: {exc}")

        if errors:
            return ProviderResult(
                "groove", "grant", False,
                f"Groove partial grant — {added} OK, errors: {'; '.join(errors)}",
            )
        return ProviderResult(
            "groove", "grant", True,
            f"Added Groove agent {email} to {added} mailbox(es) for role '{role}'",
            {"added_to_mailboxes": added},
        )
