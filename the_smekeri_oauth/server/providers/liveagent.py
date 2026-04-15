"""
LiveAgent provider — customer support / helpdesk platform.

Expected credentials dict keys:
    api_key     LiveAgent API key (LiveAgent → Configuration → API → Your API Keys)
    subdomain   Your LiveAgent subdomain (e.g. "company" for company.ladesk.com)

Revoke: sets agent status to "I" (Inactive) — the agent can no longer log in
        or receive tickets.
Grant:  sets agent status back to "A" (Active).

API docs: https://www.liveagent.com/app/page/api-documentation
Base URL:  https://{subdomain}.ladesk.com/api/v3/
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class LiveAgentProvider(BaseProvider):
    name = "liveagent"

    def _base_url(self, credentials: dict) -> str:
        subdomain = credentials["subdomain"]
        return f"https://{subdomain}.ladesk.com/api/v3"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "apikey": credentials["api_key"],
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _find_agent(self, email: str, credentials: dict) -> dict | None:
        base = self._base_url(credentials)
        headers = self._auth_headers(credentials)
        try:
            resp = requests.get(
                f"{base}/agents",
                headers=headers,
                params={"_filters": f"email:{email}"},
                timeout=30,
            )
            resp.raise_for_status()
            agents = resp.json() if isinstance(resp.json(), list) else resp.json().get("response", [])
            for agent in agents:
                if agent.get("email", "").lower() == email.lower():
                    return agent
            return None
        except requests.RequestException as exc:
            logger.error("LiveAgent agent lookup error: %s", exc)
            return None

    def _set_status(self, agent_id: str, status: str, credentials: dict) -> requests.Response:
        base = self._base_url(credentials)
        return requests.put(
            f"{base}/agents/{agent_id}",
            headers=self._auth_headers(credentials),
            json={"status": status},
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        agent = self._find_agent(email, credentials)
        if not agent:
            return ProviderResult(
                "liveagent", "revoke", True,
                f"LiveAgent agent {email} not found — already removed or never added",
            )

        agent_id = agent.get("agentid") or agent.get("id", "")
        if agent.get("status") == "I":
            return ProviderResult(
                "liveagent", "revoke", True,
                f"LiveAgent agent {email} is already inactive",
                {"agent_id": agent_id},
            )

        try:
            resp = self._set_status(agent_id, "I", credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "liveagent", "revoke", True,
                    f"Deactivated LiveAgent agent {email} (id={agent_id})",
                    {"agent_id": agent_id},
                )
            return ProviderResult(
                "liveagent", "revoke", False,
                f"LiveAgent deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("LiveAgent revoke error for %s: %s", email, exc)
            return ProviderResult("liveagent", "revoke", False, str(exc))

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
                "liveagent", "grant", False,
                f"LiveAgent agent {email} not found — create their agent account first",
            )

        agent_id = agent.get("agentid") or agent.get("id", "")
        if agent.get("status") == "A":
            return ProviderResult(
                "liveagent", "grant", True,
                f"LiveAgent agent {email} is already active for role '{role}'",
                {"agent_id": agent_id},
            )

        try:
            resp = self._set_status(agent_id, "A", credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "liveagent", "grant", True,
                    f"Re-activated LiveAgent agent {email} for role '{role}' (id={agent_id})",
                    {"agent_id": agent_id},
                )
            return ProviderResult(
                "liveagent", "grant", False,
                f"LiveAgent re-activation failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("LiveAgent grant error for %s: %s", email, exc)
            return ProviderResult("liveagent", "grant", False, str(exc))
