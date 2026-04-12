"""
Company-side agent.

Runs on the client company's infrastructure.  Polls the HR/ERP system for
employee changes and POSTs structured payloads to the server.

Usage:
    python -m agent.agent                          # uses agent_config.yaml
    python -m agent.agent --config /path/to.yaml
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

from .config import AgentConfig, load_config
from .connectors.base import BaseConnector
from .connectors.frappe import FrappeConnector
from .state import diff_snapshots, load_state, save_state

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("accessguard.agent")


# ---------------------------------------------------------------------------
# Connector factory
# ---------------------------------------------------------------------------

def build_connector(cfg: AgentConfig) -> BaseConnector:
    c = cfg.connector
    if c.type == "frappe":
        return FrappeConnector(c.base_url, c.api_key, c.api_secret)
    raise ValueError(f"Unknown connector type: {c.type!r}")


# ---------------------------------------------------------------------------
# Role → providers / entitlements
# ---------------------------------------------------------------------------

def _role_access_spec(role: str, cfg: AgentConfig) -> dict[str, dict] | None:
    """Return provider → {grant, revoke} spec when ``role_access_map`` matches."""
    role_l = (role or "").lower()
    if not role_l or not cfg.role_access_map:
        return None
    for pattern, spec in cfg.role_access_map.items():
        if pattern.lower() == role_l:
            return spec
    return None


def providers_for_role(role: str, cfg: AgentConfig) -> list[str]:
    """SaaS provider names for this role (``role_access_map`` overrides ``role_provider_map``)."""
    spec = _role_access_spec(role, cfg)
    if spec:
        return list(spec.keys())
    role_l = (role or "").lower()
    for pattern, providers in cfg.role_provider_map.items():
        if pattern.lower() == role_l:
            return providers
    return cfg.default_providers


def _entitlements(role: str, provider: str, cfg: AgentConfig, kind: str) -> list[dict]:
    spec = _role_access_spec(role, cfg)
    if not spec:
        return []
    pinfo = spec.get(provider)
    if pinfo is None:
        for k, v in spec.items():
            if k.lower() == provider.lower():
                pinfo = v
                break
    if not isinstance(pinfo, dict):
        return []
    raw = pinfo.get(kind, [])
    return list(raw) if isinstance(raw, list) else []


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_payload(change: dict, cfg: AgentConfig) -> dict:
    action = change["action_type"]
    prev_role = change.get("previous_role")
    new_role = change.get("new_role")

    access_changes: list[dict] = []

    if action == "terminated":
        for p in providers_for_role(prev_role or "", cfg):
            access_changes.append(
                {
                    "provider": p,
                    "action": "revoke",
                    "entitlements": _entitlements(prev_role or "", p, cfg, "revoke"),
                },
            )
    elif action == "added":
        for p in providers_for_role(new_role or "", cfg):
            access_changes.append(
                {
                    "provider": p,
                    "action": "grant",
                    "entitlements": _entitlements(new_role or "", p, cfg, "grant"),
                },
            )
    else:  # role_changed
        prev_ps = providers_for_role(prev_role or "", cfg)
        new_ps = providers_for_role(new_role or "", cfg)
        prev_set, new_set = set(prev_ps), set(new_ps)
        for p in prev_set - new_set:
            access_changes.append(
                {
                    "provider": p,
                    "action": "revoke",
                    "entitlements": _entitlements(prev_role or "", p, cfg, "revoke"),
                },
            )
        for p in new_set - prev_set:
            access_changes.append(
                {
                    "provider": p,
                    "action": "grant",
                    "entitlements": _entitlements(new_role or "", p, cfg, "grant"),
                },
            )

    saas_revoke = [c["provider"] for c in access_changes if c["action"] == "revoke"]
    saas_grant = [c["provider"] for c in access_changes if c["action"] == "grant"]

    return {
        "company_id": cfg.company_id,
        "company_name": cfg.company_name,
        "employee_email": change["email"],
        "employee_name": change["name"],
        "action_type": action,
        "previous_role": prev_role,
        "new_role": new_role,
        "timestamp": datetime.utcnow().isoformat(),
        "event_id": str(uuid.uuid4()),
        "access_changes": access_changes,
        "saas_revoke": saas_revoke,
        "saas_grant": saas_grant,
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# HTTP sender
# ---------------------------------------------------------------------------

def send_payload(payload: dict, cfg: AgentConfig) -> tuple[bool, dict]:
    """Send payload to server. Returns (success, parsed_response)."""
    if not cfg.server_url:
        logger.error("server_url is not configured — cannot send payload")
        return False, {}

    headers = {"Content-Type": "application/json"}
    if cfg.server_api_key:
        headers["X-API-Key"] = cfg.server_api_key

    try:
        resp = requests.post(
            f"{cfg.server_url.rstrip('/')}/api/v1/events",
            json=payload,
            headers=headers,
            timeout=30,
        )
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass

        if resp.status_code in (200, 201, 202):
            logger.info(
                "Payload accepted for %s (%s)",
                payload["employee_email"],
                payload["action_type"],
            )
            return True, body

        logger.error(
            "Server rejected payload for %s: %d %s",
            payload["employee_email"],
            resp.status_code,
            resp.text[:200],
        )
        return False, body
    except requests.RequestException as exc:
        logger.error("Failed to send payload for %s: %s", payload["employee_email"], exc)
        return False, {}


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def run_once(connector: BaseConnector, cfg: AgentConfig) -> None:
    from .dashboard_state import state as dash_state

    logger.info("Polling %s connector…", cfg.connector.type)
    scan = dash_state.start_scan()

    current_employees = connector.get_all_employees()
    if not current_employees:
        logger.warning("No employees returned from connector — skipping cycle")
        return

    previous_state = load_state(cfg.state_file)
    changes = diff_snapshots(previous_state, current_employees)

    if not changes:
        logger.info("No changes detected")
    else:
        logger.info("%d change(s) detected", len(changes))
        for change in changes:
            payload = build_payload(change, cfg)
            success, response = send_payload(payload, cfg)
            dash_state.record_change(scan, change, payload, success, response)

    save_state(cfg.state_file, current_employees)


def main(config_path: str = "agent_config.yaml") -> None:
    from .dashboard_state import state as dash_state
    from .dashboard import start_dashboard_thread

    cfg = load_config(config_path)

    if not cfg.company_id:
        logger.error("company_id is not set. Check agent_config.yaml or AGENT_COMPANY_ID env var.")
        sys.exit(1)

    connector = build_connector(cfg)

    if not connector.health_check():
        logger.error("Connector health check failed — aborting")
        sys.exit(1)

    dash_state.init(cfg)

    if cfg.dashboard_enabled:
        start_dashboard_thread(port=cfg.dashboard_port)
        logger.info("Dashboard available at http://127.0.0.1:%d", cfg.dashboard_port)

    logger.info(
        "Agent started for company '%s' (poll interval: %ds)",
        cfg.company_name,
        cfg.poll_interval,
    )

    # Run immediately on startup, then on interval
    run_once(connector, cfg)
    while True:
        next_scan = datetime.utcnow() + timedelta(seconds=cfg.poll_interval)
        dash_state.set_next_scan(next_scan)
        time.sleep(cfg.poll_interval)
        run_once(connector, cfg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AccessGuard Agent")
    parser.add_argument("--config", default="agent_config.yaml")
    args = parser.parse_args()
    main(args.config)
