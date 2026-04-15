"""
Generic webhook provider — escape hatch for SaaS tools without a dedicated module.

Use this when a vendor does not have a public REST API for user management but
does expose a webhook endpoint that accepts provisioning/deprovisioning payloads.

Credentials keys:
    webhook_url        Full URL for both grant/revoke (optional if base_url + paths set)
    base_url           Base URL (e.g. https://api.vendor.com)
    grant_path         Path for grant requests  (default: /grant)
    revoke_path        Path for revoke requests (default: /revoke)
    method             HTTP method for both actions (default: POST)
    timeout            Request timeout in seconds (default: 30)
    headers            Optional dict with extra headers (e.g. Authorization)
    static_payload     Optional dict merged into every request body

Example credentials to configure in the admin panel:
    {
      "base_url": "https://my-internal-idp.company.com",
      "grant_path": "/api/users/enable",
      "revoke_path": "/api/users/disable",
      "headers": {"X-API-Key": "secret"},
      "static_payload": {"source": "accessguard"}
    }
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class GenericWebhookProvider(BaseProvider):
    name = "generic_webhook"

    def _build_url(self, credentials: dict, action: str) -> str:
        webhook_url = str(credentials.get("webhook_url", "")).strip()
        if webhook_url:
            return webhook_url

        base = str(credentials.get("base_url", "")).rstrip("/")
        if not base:
            raise ValueError(
                "Missing provider credentials: set 'webhook_url' or 'base_url'",
            )
        default_path = "/grant" if action == "grant" else "/revoke"
        path_key = "grant_path" if action == "grant" else "revoke_path"
        path = str(credentials.get(path_key, default_path))
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    def _request(
        self,
        action: str,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None,
    ) -> ProviderResult:
        try:
            url = self._build_url(credentials, action)
        except ValueError as exc:
            return ProviderResult(provider=self.name, action=action, success=False, message=str(exc))

        method = str(credentials.get("method", "POST")).upper()
        timeout = int(credentials.get("timeout", 30))
        headers: dict[str, str] = {"Content-Type": "application/json"}
        extra_headers = credentials.get("headers")
        if isinstance(extra_headers, dict):
            headers.update({str(k): str(v) for k, v in extra_headers.items()})

        payload: dict[str, Any] = {
            "provider": self.name,
            "action": action,
            "email": email,
            "role": role,
            "entitlements": entitlements or [],
        }
        static_payload = credentials.get("static_payload")
        if isinstance(static_payload, dict):
            payload.update(static_payload)

        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            if 200 <= resp.status_code < 300:
                return ProviderResult(
                    provider=self.name,
                    action=action,
                    success=True,
                    message=f"{action.capitalize()} request accepted for {email}",
                    details={"status_code": resp.status_code, "url": url},
                )
            return ProviderResult(
                provider=self.name,
                action=action,
                success=False,
                message=f"{action.capitalize()} failed: {resp.status_code} {resp.text[:200]}",
                details={"status_code": resp.status_code, "url": url},
            )
        except requests.RequestException as exc:
            logger.error("%s request error for %s (%s): %s", self.name, email, action, exc)
            return ProviderResult(provider=self.name, action=action, success=False, message=str(exc))

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        return self._request("revoke", email, "", credentials, entitlements)

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        return self._request("grant", email, role, credentials, entitlements)


# Keep an empty dict for backwards compatibility — nothing is pre-registered here.
# All previously stub-registered providers now have dedicated implementation modules.
GENERIC_PROVIDER_CLASSES: dict[str, type[GenericWebhookProvider]] = {}
