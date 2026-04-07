# AccessGuard

Automated SaaS access management. Detects employee changes (termination, role change, new hire) via a lightweight company-side agent and automatically revokes or grants access across Microsoft 365 and Google Workspace.

---

## Table of Contents

1. [How the System Works End-to-End](#1-how-the-system-works-end-to-end)
2. [Testing Locally Without Real Credentials](#2-testing-locally-without-real-credentials)
3. [Real-World Company Onboarding Flow](#3-real-world-company-onboarding-flow)
4. [Architecture Reference](#4-architecture-reference)

---

## 1. How the System Works End-to-End

### The Two Components

```
┌─────────────────────────────────┐         ┌──────────────────────────────────┐
│     Company Infrastructure      │         │        AccessGuard Server         │
│                                 │         │                                  │
│  ┌─────────────────────────┐    │  HTTPS  │  ┌────────────────────────────┐  │
│  │   AccessGuard Agent     │────┼────────▶│  │    FastAPI (main.py)       │  │
│  │                         │    │  POST   │  │    POST /api/v1/events     │  │
│  │  • Polls HR/ERP system  │    │ payload │  └────────────┬───────────────┘  │
│  │  • Detects changes      │    │         │               │                  │
│  │  • Builds JSON payload  │    │         │  ┌────────────▼───────────────┐  │
│  │  • Sends to server      │    │         │  │    Execution Router        │  │
│  └─────────────────────────┘    │         │  │    (services/router.py)    │  │
│             │                   │         │  └────────────┬───────────────┘  │
│  ┌──────────▼──────────────┐    │         │               │                  │
│  │   Company HR/ERP        │    │         │   ┌───────────┴────────────┐    │
│  │   (Frappe, SQL, etc.)   │    │         │   ▼                        ▼    │
│  └─────────────────────────┘    │         │  Microsoft              Google   │
│                                 │         │  Provider               Provider │
└─────────────────────────────────┘         │     │                      │     │
                                            │  ┌──▼──────────────────────▼──┐  │
                                            │  │        Audit Log DB         │  │
                                            │  └─────────────────────────────┘  │
                                            │                                  │
                                            │  ┌──────────────────────────────┐ │
                                            │  │   Dashboard (/)              │ │
                                            │  │   Admin Panel (/api/v1/admin)│ │
                                            │  └──────────────────────────────┘ │
                                            └──────────────────────────────────┘
```

### Step-by-Step Flow

**Every N minutes (configurable), the agent runs:**

1. **Agent polls** the company's Frappe/ERP system for all employees
2. **State diff** — compares current employees vs the last known snapshot (`.agent_state.json`)
3. **Change detected** — agent classifies it as one of:
   - `added` — new employee in the system
   - `terminated` — employee status changed to "Left"
   - `role_changed` — designation changed
4. **Provider resolution** — the agent uses `role_provider_map` in `agent_config.yaml` to determine which SaaS providers the old/new role requires
5. **Payload built** and POSTed to `POST /api/v1/events` with `X-API-Key` header
6. **Server authenticates** the request using the company's `agent_api_key` stored in the DB
7. **Router** iterates over `saas_revoke` and `saas_grant` in the payload
8. **For each provider**: loads encrypted credentials from DB, instantiates the provider, calls `revoke()` or `grant()`
9. **Each provider** calls the real API (Microsoft Graph / Google Admin SDK)
10. **Every result** is written to the `audit_logs` table
11. **Dashboard** shows the result in real time

### The Payload Format

```json
{
  "company_id": "acme-corp",
  "company_name": "Acme Corp",
  "employee_email": "john.doe@acme.com",
  "employee_name": "John Doe",
  "action_type": "terminated",
  "previous_role": "Software Engineer",
  "new_role": null,
  "timestamp": "2025-04-07T10:30:00Z",
  "saas_revoke": ["microsoft", "google"],
  "saas_grant": [],
  "metadata": {}
}
```

### How Provider Credentials Are Secured

Credentials (tenant IDs, client secrets, service account keys) are stored
**encrypted in the database** using [Fernet symmetric encryption](https://cryptography.io/en/latest/fernet/).
The encryption key lives only in the server's `ENCRYPTION_KEY` environment variable — never in the DB.

---

## 2. Testing Locally Without Real Credentials

AccessGuard ships with **mock providers** (`mock_microsoft`, `mock_google`) that simulate
real API calls without touching any external service.

### Quick Start (5 minutes)

#### Step 1 — Generate an encryption key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

#### Step 2 — Create `server/.env`

```env
DATABASE_URL=sqlite:///./accessguard.db
ENCRYPTION_KEY=<paste key from step 1>
ADMIN_API_KEY=change-me-strong-admin-key
AGENT_API_KEY=change-me-strong-agent-key
AUTH_ENABLED=false          # skip auth for local testing
```

#### Step 3 — Install dependencies and start the server

```bash
pip install -r requirements.txt
uvicorn server.main:app --reload
```

#### Step 4 — Run the automated test suite

```bash
python test_local.py
```

This will:
- Create a `demo-corp` company
- Configure `mock_microsoft` and `mock_google` providers
- Set up role mappings (CEO, Engineer, Intern, etc.)
- Send 4 test payloads (new employee, role change, termination, missing credentials)
- Verify audit logs and stats
- Print a full summary

#### Step 5 — Open the dashboard

```
http://localhost:8000
```

Admin API key: `dev-admin-key-change-me`

---

### Mock Employee Database (for agent testing)

Copy this to `agent_config.yaml` and create a `mock_employees.json` alongside the agent:

**`agent_config.yaml`** (for local testing):
```yaml
company_id: "demo-corp"
company_name: "Demo Corp"
server_url: "http://localhost:8000"
server_api_key: "dev-agent-key-change-me"
poll_interval: 10    # 10 seconds for fast testing

role_provider_map:
  "CEO":               ["mock_microsoft", "mock_google"]
  "Software Engineer": ["mock_microsoft", "mock_google"]
  "Accountant":        ["mock_microsoft"]
  "Intern":            ["mock_microsoft"]

default_providers: ["mock_microsoft"]

connector:
  type: "frappe"
  base_url: "http://localhost:8001"   # a local Frappe dev instance, or see below
```

**If you don't have a Frappe instance**, you can test the agent's change detection logic
by directly calling the server's event endpoint. The test scenarios below use `curl`:

---

### Test Scenarios with curl

All examples assume `AUTH_ENABLED=false` and the server at `localhost:8000`.

#### Scenario A — New employee added
```bash
curl -s -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-agent-key-change-me" \
  -d '{
    "company_id": "demo-corp",
    "company_name": "Demo Corp",
    "employee_email": "alice.johnson@democorp.com",
    "employee_name": "Alice Johnson",
    "action_type": "added",
    "previous_role": null,
    "new_role": "Software Engineer",
    "saas_revoke": [],
    "saas_grant": ["mock_microsoft", "mock_google"]
  }' | python -m json.tool
```

**Expected result**: `all_succeeded: true`, two `grant` log entries.

---

#### Scenario B — Role change (Intern → Software Engineer)
```bash
curl -s -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-agent-key-change-me" \
  -d '{
    "company_id": "demo-corp",
    "company_name": "Demo Corp",
    "employee_email": "bob.smith@democorp.com",
    "employee_name": "Bob Smith",
    "action_type": "role_changed",
    "previous_role": "Intern",
    "new_role": "Software Engineer",
    "saas_revoke": ["mock_microsoft"],
    "saas_grant": ["mock_microsoft", "mock_google"]
  }' | python -m json.tool
```

**Expected result**: One `revoke` and two `grant` entries in logs.

---

#### Scenario C — Employee terminated
```bash
curl -s -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-agent-key-change-me" \
  -d '{
    "company_id": "demo-corp",
    "company_name": "Demo Corp",
    "employee_email": "carol.white@democorp.com",
    "employee_name": "Carol White",
    "action_type": "terminated",
    "previous_role": "CEO",
    "new_role": null,
    "saas_revoke": ["mock_microsoft", "mock_google"],
    "saas_grant": []
  }' | python -m json.tool
```

**Expected result**: Two `revoke` entries, `all_succeeded: true`.

---

#### Check logs
```bash
curl -s "http://localhost:8000/api/v1/logs?company_id=demo-corp&limit=10" | python -m json.tool
```

#### Check stats
```bash
curl -s "http://localhost:8000/api/v1/logs/stats?company_id=demo-corp" | python -m json.tool
```

---

### What "mock" means vs production

| | Mock providers | Real providers |
|---|---|---|
| API calls | None — just logs | Microsoft Graph / Google Admin SDK |
| Credentials required | No (empty `{}` works) | Yes — tenant IDs, secrets, service accounts |
| Sessions actually revoked | No | Yes |
| Routing, logging, DB writes | Full | Full |
| Use for | Dev / CI / demos | Production |

To switch from mock to real, change provider names in `saas_revoke`/`saas_grant`
from `mock_microsoft` → `microsoft` and `mock_google` → `google`, then add
real credentials via the admin panel.

---

## 3. Real-World Company Onboarding Flow

Use this section as a step-by-step guide during client meetings.

---

### Before the Meeting

**We prepare:**
- Our AccessGuard server URL (e.g. `https://accessguard.yourdomain.com`)
- Admin credentials to our panel
- The agent package (`agent/` directory + `requirements.txt`)
- The example config file (`agent/agent_config.yaml.example`)

---

### Step 1 — Add the company in our admin panel

```
POST /api/v1/admin/companies
{
  "company_id": "acme-corp",        ← we choose this (lowercase, no spaces)
  "company_name": "Acme Corp",
  "agent_api_key": "<random 32-char secret>",
  "enabled": true
}
```

> **What this is**: The `agent_api_key` is the shared secret between the client's agent
> and our server. It authenticates every event payload. Treat it like a password.

---

### Step 2 — Configure providers for this company

For **Microsoft 365**, we need from the client:
- Azure Tenant ID
- App Registration Client ID
- App Registration Client Secret

```
PUT /api/v1/admin/companies/acme-corp/providers/microsoft
{
  "provider_name": "microsoft",
  "credentials": {
    "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_id":  "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
    "client_secret": "very-secret-value"
  },
  "enabled": true
}
```

For **Google Workspace**, we need from the client:
- Service account JSON key file (with domain-wide delegation enabled)
- Admin email (impersonation account)

```
PUT /api/v1/admin/companies/acme-corp/providers/google
{
  "provider_name": "google",
  "credentials": {
    "service_account_info": { ...entire JSON key file as object... },
    "admin_email": "admin@acme.com"
  },
  "enabled": true
}
```

> Credentials are **encrypted with Fernet** before being stored. The raw values
> are never retrievable via the API — only the server can decrypt them at runtime.

---

### Step 3 — Define role mappings

We ask the client: "For each job title in your HR system, which tools should an employee have?"

```
PUT /api/v1/admin/companies/acme-corp/roles/CEO
{ "role_name": "CEO", "providers": ["microsoft", "google"] }

PUT /api/v1/admin/companies/acme-corp/roles/Accountant
{ "role_name": "Accountant", "providers": ["microsoft"] }

PUT /api/v1/admin/companies/acme-corp/roles/Intern
{ "role_name": "Intern", "providers": ["microsoft"] }
```

All of this is also manageable through the **admin panel UI** at `https://accessguard.yourdomain.com`.

---

### Step 4 — Install the agent on the client's server

We hand the client the `agent/` directory. They install it on any machine that:
- Can reach their Frappe/ERP system
- Can reach our server over HTTPS

```bash
pip install -r requirements.txt
cp agent_config.yaml.example agent_config.yaml
```

They fill in `agent_config.yaml`:
```yaml
company_id: "acme-corp"
company_name: "Acme Corp"
server_url: "https://accessguard.yourdomain.com"
server_api_key: "<the key we generated in Step 1>"
poll_interval: 900         # 15 minutes

role_provider_map:
  "CEO":         ["microsoft", "google"]
  "Accountant":  ["microsoft"]
  "Intern":      ["microsoft"]

connector:
  type: "frappe"
  base_url: "https://erp.acme.com"

# Credentials via env vars (recommended)
# FRAPPE_API_KEY and FRAPPE_API_SECRET
```

Then they run:
```bash
python -m agent.agent
```

Or as a systemd service for production.

---

### Step 5 — First sync

On first run, the agent:
1. Fetches **all current employees** from Frappe
2. Saves the state to `.agent_state.json`
3. Since there is **no previous state**, all employees are treated as "seen for the first time" — **no payloads are sent**

This means the first run is safe — it only establishes the baseline. Payloads are only sent from the **second run onwards** when actual changes are detected.

---

### What happens when an employee changes role

1. Agent polls Frappe → sees `designation` changed from `"Intern"` to `"Software Engineer"`
2. Compares against saved state → detects `role_changed`
3. Resolves providers: `Intern` had `[microsoft]`, `Software Engineer` has `[microsoft, google]`
4. Builds payload:
   ```json
   {
     "action_type": "role_changed",
     "saas_revoke": [],          ← microsoft is in both, no change needed
     "saas_grant":  ["google"]   ← only the difference
   }
   ```
5. Server receives payload → calls `google.grant("employee@acme.com", "Software Engineer", credentials)`
6. Audit log entry created — visible in client's dashboard

---

### What happens when someone is terminated

1. Agent polls Frappe → sees `status: "Left"` for an employee
2. Detects `terminated`
3. Resolves **all providers** the previous role had access to
4. Builds payload:
   ```json
   {
     "action_type": "terminated",
     "saas_revoke": ["microsoft", "google"],
     "saas_grant":  []
   }
   ```
5. Server calls:
   - `microsoft.revoke()` → revokes sign-in sessions + deletes all OAuth permission grants
   - `google.revoke()` → deletes all OAuth tokens for the user
6. Two audit log entries created — both shown in dashboard as "Terminated"

---

### What logs the company sees

The client can open the AccessGuard dashboard at any time and see:

| Timestamp | Employee | Action | Provider | Operation | Status |
|---|---|---|---|---|---|
| 2025-04-07 10:30 | Carol White (carol@acme.com) | ✕ Terminated | microsoft | revoke | ✓ Success |
| 2025-04-07 10:30 | Carol White (carol@acme.com) | ✕ Terminated | google | revoke | ✓ Success |
| 2025-04-07 09:15 | Bob Smith (bob@acme.com) | ↺ Role Changed | google | grant | ✓ Success |
| 2025-04-06 14:00 | Alice Johnson (alice@acme.com) | + Added | microsoft | grant | ✓ Success |

Filtering by company and date range is supported. Stats (total / succeeded / failed) are
shown at the top.

---

## 4. Architecture Reference

### Folder Structure

```
accessguard/
├── shared/
│   └── schema.py             # Canonical AgentPayload & ProviderResult models
│
├── agent/                    # Deployed at the client company
│   ├── agent.py              # Main polling loop
│   ├── config.py             # YAML + env var config
│   ├── state.py              # Change detection (diff snapshots)
│   ├── connectors/
│   │   ├── base.py           # EmployeeRecord + BaseConnector ABC
│   │   └── frappe.py         # Frappe/ERPNext connector
│   └── agent_config.yaml.example
│
├── server/                   # Our infrastructure
│   ├── main.py               # FastAPI entry point
│   ├── config.py             # Pydantic-settings
│   ├── database/
│   │   ├── db.py             # SQLAlchemy engine + session
│   │   └── models.py         # ORM: Company, CompanyProvider, RoleMapping, AuditLog
│   ├── models/               # Pydantic request/response schemas
│   ├── providers/
│   │   ├── base.py           # BaseProvider ABC
│   │   ├── registry.py       # Dynamic provider lookup
│   │   ├── microsoft.py      # Microsoft Graph API
│   │   ├── google.py         # Google Workspace Admin SDK
│   │   └── mock.py           # Mock providers for testing
│   ├── services/
│   │   ├── router.py         # Orchestrates provider calls
│   │   ├── credential_service.py   # Fernet encrypt/decrypt
│   │   └── log_service.py    # Audit log CRUD
│   ├── admin/
│   │   └── routes.py         # Admin CRUD API (X-Admin-Key auth)
│   └── dashboard/
│       └── index.html        # Single-page dashboard
│
├── test_local.py             # End-to-end local test (no real credentials)
└── requirements.txt
```

### Adding a New Provider

1. Create `server/providers/slack.py`, subclass `BaseProvider`
2. Implement `revoke(email, credentials)` and `grant(email, role, credentials)`
3. Add to `server/providers/__init__.py`:
   ```python
   from .slack import SlackProvider
   register_provider("slack", SlackProvider)
   ```
4. That's it. The router, admin panel, and agent config pick it up automatically.

### Environment Variables (server)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./accessguard.db` |
| `ENCRYPTION_KEY` | Fernet key for credential encryption | *(required)* |
| `ADMIN_API_KEY` | Key for `/api/v1/admin/*` routes | `change-me` |
| `AGENT_API_KEY` | Global fallback agent key | *(optional)* |
| `AUTH_ENABLED` | Set `false` to skip auth (dev only) | `true` |
