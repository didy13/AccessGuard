"""
AccessGuard — local end-to-end test script.

Tests the full pipeline without real SaaS credentials by using the
mock_microsoft and mock_google providers.

Usage:
    # Terminal 1 — start the server
    cd server
    AUTH_ENABLED=false uvicorn server.main:app --reload

    # Terminal 2 — run this script
    python test_local.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

from agent.agent import build_payload
from agent.config import AgentConfig
from shared.schema import normalize_provider_name

BASE = "http://localhost:8000"
# Read API keys from environment so test matches current server config.
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "admin1234567891011")
AGENT_KEY = os.getenv("AGENT_API_KEY", "agent1234567891011")
COMPANY_ID = "demo-corp"

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"

EXPECTED_SAAS_PROVIDERS = {
    "microsoft",
    "google",
    "bamboohr",
    "clockify",
    "zoho",
    "informatika365",
    "erpag",
    "workday",
    "rippling",
    "sage_hrms",
    "jira",
    "freshbooks",
    "hubspot",
    "salesforce",
    "sap_s4hana_cloud",
    "oracle_fusion_erp",
    "microsoft_dynamics_365",
    "liveagent",
    "groove",
    "happyfox",
}
GENERIC_PREVIEW_PROVIDERS = [
    "jira",
    "freshbooks",
    "hubspot",
    "salesforce",
    "happyfox",
]


def ok(msg: str) -> None:
    print(f"  {PASS} {msg}")


def fail(msg: str) -> None:
    print(f"  {FAIL} {msg}")
    sys.exit(1)


def info(msg: str) -> None:
    print(f"\n{INFO} {msg}")


def admin_post(path: str, data: dict) -> dict:
    r = session.post(
        BASE + path,
        json=data,
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    if r.status_code not in (200, 201):
        fail(f"POST {path} → {r.status_code}: {r.text}")
    return r.json()


def admin_put(path: str, data: dict) -> dict:
    r = session.put(
        BASE + path,
        json=data,
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    if r.status_code not in (200, 201):
        fail(f"PUT {path} → {r.status_code}: {r.text}")
    return r.json()


def admin_get(path: str) -> dict:
    r = session.get(
        BASE + path,
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    if r.status_code not in (200, 201):
        fail(f"GET {path} → {r.status_code}: {r.text}")
    return r.json()


def send_event(payload: dict) -> dict:
    r = session.post(
        BASE + "/api/v1/events",
        json=payload,
        headers={"X-API-Key": AGENT_KEY},
    )
    if r.status_code not in (200, 201, 202):
        fail(f"POST /api/v1/events → {r.status_code}: {r.text}")
    return r.json()


def get_logs(company_id: str | None = None, limit: int = 10) -> list:
    qs = f"?limit={limit}"
    if company_id:
        qs += f"&company_id={company_id}"
    r = session.get(BASE + "/api/v1/logs" + qs)
    return r.json()


def get_stats(company_id: str | None = None) -> dict:
    qs = f"?company_id={company_id}" if company_id else ""
    r = session.get(BASE + "/api/v1/logs/stats" + qs)
    return r.json()


# ── Payload factory ───────────────────────────────────────────────────────────

def make_payload(
    action: str,
    email: str,
    name: str,
    prev_role: str | None = None,
    new_role: str | None = None,
    revoke: list[str] | None = None,
    grant: list[str] | None = None,
    access_changes: list[dict] | None = None,
    event_id: str | None = None,
) -> dict:
    body: dict = {
        "company_id": COMPANY_ID,
        "company_name": "Demo Corp",
        "employee_email": email,
        "employee_name": name,
        "action_type": action,
        "previous_role": prev_role,
        "new_role": new_role,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {"test": True},
    }
    if event_id:
        body["event_id"] = event_id
    if access_changes is not None:
        body["access_changes"] = access_changes
        body["saas_revoke"] = []
        body["saas_grant"] = []
    else:
        body["saas_revoke"] = revoke or []
        body["saas_grant"] = grant or []
    return body


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_company() -> None:
    info("Setting up demo company…")

    # Create company (ignore if already exists)
    r = session.post(
        BASE + "/api/v1/admin/companies",
        json={
            "company_id": COMPANY_ID,
            "company_name": "Demo Corp",
            "agent_api_key": AGENT_KEY,
            "enabled": True,
        },
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    if r.status_code == 400 and "already exists" in r.text:
        ok("Company already exists — skipping creation")
    elif r.status_code in (200, 201):
        ok("Company created")
    else:
        fail(f"Create company: {r.status_code} {r.text}")

    # Configure mock providers (empty credentials are fine for mock)
    for provider in ("mock_microsoft", "mock_google"):
        admin_put(
            f"/api/v1/admin/companies/{COMPANY_ID}/providers/{provider}",
            {"provider_name": provider, "credentials": {}, "enabled": True},
        )
        ok(f"Provider configured: {provider}")

    # Configure a handful of generic providers for "how it looks" preview.
    # Port 9 deliberately refuses quickly, so tests stay fast and deterministic.
    generic_credentials = {
        "webhook_url": "http://127.0.0.1:9/accessguard/jml",
        "timeout": 1,
    }
    for provider in GENERIC_PREVIEW_PROVIDERS:
        admin_put(
            f"/api/v1/admin/companies/{COMPANY_ID}/providers/{provider}",
            {"provider_name": provider, "credentials": generic_credentials, "enabled": True},
        )
        ok(f"Preview provider configured: {provider}")

    # Role → provider mappings
    role_map = {
        "CEO":                     ["mock_microsoft", "mock_google"],
        "Software Engineer":       ["mock_microsoft", "mock_google"],
        "Finance Manager":         ["mock_microsoft", "mock_google"],
        "Accountant":              ["mock_microsoft"],
        "Intern":                  ["mock_microsoft"],
    }
    for role, providers in role_map.items():
        admin_put(
            f"/api/v1/admin/companies/{COMPANY_ID}/roles/{role}",
            {"role_name": role, "providers": providers},
        )
    ok(f"Role mappings configured ({len(role_map)} roles)")


# ── Test scenarios ────────────────────────────────────────────────────────────

def test_new_employee() -> None:
    info("Scenario 1: New employee added (Software Engineer)")
    payload = make_payload(
        action="added",
        email="alice.johnson@democorp.com",
        name="Alice Johnson",
        new_role="Software Engineer",
        grant=["mock_microsoft", "mock_google"],
    )
    result = send_event(payload)
    assert result["action_type"] == "added", f"Wrong action: {result}"
    assert result["all_succeeded"], f"Not all succeeded: {result['results']}"
    assert len(result["results"]) == 2, f"Expected 2 provider results, got {len(result['results'])}"
    ok(f"Event accepted — {len(result['results'])} provider(s) triggered")
    for r in result["results"]:
        ok(f"  {r['provider']}.{r['action']} → {r['message']}")


def test_role_change() -> None:
    info("Scenario 2: Role change — Intern promoted to Software Engineer")
    payload = make_payload(
        action="role_changed",
        email="bob.smith@democorp.com",
        name="Bob Smith",
        prev_role="Intern",
        new_role="Software Engineer",
        revoke=["mock_microsoft"],               # Intern had only Microsoft
        grant=["mock_google"],                    # SE additionally needs Google
    )
    result = send_event(payload)
    assert result["action_type"] == "role_changed"
    assert result["all_succeeded"]
    ok(f"Role change processed — revoke: {[r['provider'] for r in result['results'] if r['action']=='revoke']}, "
       f"grant: {[r['provider'] for r in result['results'] if r['action']=='grant']}")


def test_mover_same_provider_entitlement_swap() -> None:
    info("Scenario 2b: mover swaps entitlements on same provider")
    cfg = AgentConfig(
        role_access_map={
            "Intern": {
                "microsoft": {
                    "grant": [{"type": "aad_group", "group_id": "intern-group"}],
                    "revoke": [{"type": "aad_group", "group_id": "intern-group"}],
                },
            },
            "Software Engineer": {
                "microsoft": {
                    "grant": [{"type": "aad_group", "group_id": "engineering-group"}],
                    "revoke": [{"type": "aad_group", "group_id": "engineering-group"}],
                },
            },
        },
    )
    payload = build_payload(
        {
            "action_type": "role_changed",
            "email": "mover.sameprovider@democorp.com",
            "name": "Mover SameProvider",
            "previous_role": "Intern",
            "new_role": "Software Engineer",
        },
        cfg,
    )
    m_ops = [c for c in payload["access_changes"] if c["provider"] == "microsoft"]
    assert any(c["action"] == "revoke" for c in m_ops), f"Expected microsoft revoke op: {m_ops}"
    assert any(c["action"] == "grant" for c in m_ops), f"Expected microsoft grant op: {m_ops}"
    ok("Mover payload includes both revoke and grant for same provider")


def test_termination() -> None:
    info("Scenario 3: Employee terminated (CEO)")
    payload = make_payload(
        action="terminated",
        email="carol.white@democorp.com",
        name="Carol White",
        prev_role="CEO",
        revoke=["mock_microsoft", "mock_google"],
    )
    result = send_event(payload)
    assert result["action_type"] == "terminated"
    assert result["all_succeeded"]
    ok(f"Termination processed — {len(result['results'])} provider(s) revoked")
    for r in result["results"]:
        ok(f"  {r['provider']} → {r['message']}")


def test_access_changes_with_entitlements() -> None:
    info("Scenario 5: access_changes with entitlements (mock providers)")
    payload = make_payload(
        action="added",
        email="erin.entitlements@democorp.com",
        name="Erin Entitlements",
        new_role="QA Engineer",
        access_changes=[
            {
                "provider": "mock_microsoft",
                "action": "grant",
                "entitlements": [{"type": "aad_group", "group_id": "demo-group"}],
            },
            {
                "provider": "mock_google",
                "action": "grant",
                "entitlements": [{"type": "workspace_group", "email": "qa@democorp.com"}],
            },
        ],
        event_id="00000000-0000-4000-8000-000000000099",
    )
    result = send_event(payload)
    assert result["all_succeeded"]
    for r in result["results"]:
        d = r.get("details") or {}
        assert d.get("entitlements"), f"Expected entitlements echo in details: {r}"


def test_all_expected_providers_are_registered() -> None:
    info("Scenario 6: all expected SaaS providers are registered on server")
    result = admin_get("/api/v1/admin/providers")
    available = set(result.get("providers", []))
    missing = sorted(EXPECTED_SAAS_PROVIDERS - available)
    assert not missing, f"Missing providers: {missing}"
    ok(f"All expected providers registered ({len(EXPECTED_SAAS_PROVIDERS)})")


def test_provider_name_normalization_aliases() -> None:
    info("Scenario 6b: provider aliases normalize to canonical names")
    assert normalize_provider_name("Microsoft 365 (Entra ID)") == "microsoft"
    assert normalize_provider_name("Azure") == "microsoft"
    assert normalize_provider_name("Google Workspace") == "google"
    assert normalize_provider_name("Zoho People") == "zoho"
    assert normalize_provider_name("SAP S/4HANA Cloud") == "sap_s4hana_cloud"
    ok("Provider alias normalization works for CSV-friendly names")


def test_policy_skips_disabled_provider() -> None:
    info("Scenario 7: provider not enabled for company is rejected (policy)")
    payload = make_payload(
        action="added",
        email="frank.policy@democorp.com",
        name="Frank Policy",
        new_role="Contractor",
        access_changes=[
            {"provider": "mock_microsoft", "action": "grant", "entitlements": []},
            {"provider": "google", "action": "grant", "entitlements": []},
        ],
    )
    result = send_event(payload)
    assert not result["all_succeeded"]
    msgs = " ".join(r.get("message", "") for r in result["results"])
    assert "not enabled" in msgs
    assert any(r.get("success") for r in result["results"])


def test_missing_provider_credentials() -> None:
    info("Scenario 8: Provider with no credentials configured (expected failure)")
    payload = make_payload(
        action="terminated",
        email="dave.brown@democorp.com",
        name="Dave Brown",
        prev_role="Engineer",
        revoke=["microsoft"],  # real provider — no credentials in demo company
    )
    result = send_event(payload)
    assert result["action_type"] == "terminated"
    failures = [r for r in result["results"] if not r["success"]]
    assert failures, "Expected at least one failure for unconfigured real provider"
    ok(f"Correctly reported failure: {failures[0]['message'][:80]}")


def test_generic_preview_flow() -> None:
    info("Scenario 9: generic SaaS preview (multi-provider response shape)")
    access_changes = [
        {"provider": p, "action": "revoke", "entitlements": [{"type": "webhook_label", "value": p}]}
        for p in GENERIC_PREVIEW_PROVIDERS
    ]
    payload = make_payload(
        action="terminated",
        email="preview.saas@democorp.com",
        name="Preview SaaS",
        prev_role="Consultant",
        access_changes=access_changes,
    )
    result = send_event(payload)
    assert result["action_type"] == "terminated"
    assert len(result["results"]) == len(GENERIC_PREVIEW_PROVIDERS)
    ok("Preview response includes all configured generic SaaS providers")
    print("\n  Generic preview results:")
    for r in result["results"]:
        status = "✓" if r["success"] else "✗"
        print(f"    [{status}] {r['provider']}.{r['action']} -> {r['message'][:80]}")


def test_logs_and_stats() -> None:
    info("Checking audit logs and stats…")
    logs = get_logs(COMPANY_ID, limit=20)
    stats = get_stats(COMPANY_ID)

    assert len(logs) >= 10, f"Expected at least 10 log entries, got {len(logs)}"
    ok(f"Log entries for {COMPANY_ID}: {len(logs)}")
    ok(f"Stats — total: {stats['total']}, succeeded: {stats['succeeded']}, failed: {stats['failed']}")

    print("\n  Most recent log entries:")
    for log in logs[:5]:
        status = "✓" if log["success"] else "✗"
        print(f"    [{status}] {log['employee_email']} | {log['provider']}.{log['action']} | {log['message'][:60]}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AccessGuard — Local End-to-End Test")
    print("=" * 60)

    # Check server is running
    try:
        requests.get(BASE + "/api/v1/logs/stats", timeout=3)
    except requests.ConnectionError:
        print(f"\n{FAIL} Server not reachable at {BASE}")
        print("  Start it with: AUTH_ENABLED=false uvicorn server.main:app --reload")
        sys.exit(1)

    ok("Server is reachable")

    setup_company()
    test_new_employee()
    test_role_change()
    test_mover_same_provider_entitlement_swap()
    test_termination()
    test_access_changes_with_entitlements()
    test_all_expected_providers_are_registered()
    test_provider_name_normalization_aliases()
    test_policy_skips_disabled_provider()
    test_missing_provider_credentials()
    test_generic_preview_flow()
    test_logs_and_stats()

    print("\n" + "=" * 60)
    print("  All tests passed!")
    print("  Dashboard: http://localhost:8000")
    print("  API docs:  http://localhost:8000/docs")
    print("=" * 60 + "\n")
