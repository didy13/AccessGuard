"""Shared in-memory state for the agent dashboard."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AgentConfig


@dataclass
class ChangeRecord:
    email: str
    name: str
    action_type: str          # terminated | added | role_changed
    previous_role: str | None
    new_role: str | None
    providers_revoked: list[str]
    providers_granted: list[str]
    server_success: bool
    server_message: str


@dataclass
class ScanRecord:
    scanned_at: datetime
    changes: list[ChangeRecord] = field(default_factory=list)

    @property
    def changes_count(self) -> int:
        return len(self.changes)

    @property
    def all_succeeded(self) -> bool:
        return all(c.server_success for c in self.changes)


class AgentDashboardState:
    _MAX_HISTORY = 100

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.company_id: str = ""
        self.company_name: str = ""
        self.connector_type: str = ""
        self.poll_interval: int = 900
        self.started_at: datetime = datetime.utcnow()
        self.last_scan: datetime | None = None
        self.next_scan: datetime | None = None
        self.scan_history: list[ScanRecord] = []

    def init(self, cfg: AgentConfig) -> None:
        with self._lock:
            self.company_id = cfg.company_id
            self.company_name = cfg.company_name
            self.connector_type = cfg.connector.type
            self.poll_interval = cfg.poll_interval

    def start_scan(self) -> ScanRecord:
        record = ScanRecord(scanned_at=datetime.utcnow())
        with self._lock:
            self.last_scan = record.scanned_at
            self.scan_history.insert(0, record)
            if len(self.scan_history) > self._MAX_HISTORY:
                self.scan_history.pop()
        return record

    def set_next_scan(self, dt: datetime) -> None:
        with self._lock:
            self.next_scan = dt

    def record_change(
        self,
        scan: ScanRecord,
        change: dict,
        payload: dict,
        success: bool,
        server_response: dict,
    ) -> None:
        message = ""
        if server_response.get("results"):
            messages = [r.get("message", "") for r in server_response["results"]]
            message = " | ".join(m for m in messages if m)
        elif not success:
            message = server_response.get("detail", "Server error")

        cr = ChangeRecord(
            email=change["email"],
            name=change["name"],
            action_type=change["action_type"],
            previous_role=change.get("previous_role"),
            new_role=change.get("new_role"),
            providers_revoked=payload.get("saas_revoke", []),
            providers_granted=payload.get("saas_grant", []),
            server_success=success,
            server_message=message,
        )
        with self._lock:
            scan.changes.append(cr)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "company_id": self.company_id,
                "company_name": self.company_name,
                "connector_type": self.connector_type,
                "poll_interval": self.poll_interval,
                "started_at": self.started_at.isoformat(),
                "last_scan": self.last_scan.isoformat() if self.last_scan else None,
                "next_scan": self.next_scan.isoformat() if self.next_scan else None,
                "scan_history": [
                    {
                        "scanned_at": s.scanned_at.isoformat(),
                        "changes_count": s.changes_count,
                        "all_succeeded": s.all_succeeded,
                        "changes": [
                            {
                                "email": c.email,
                                "name": c.name,
                                "action_type": c.action_type,
                                "previous_role": c.previous_role,
                                "new_role": c.new_role,
                                "providers_revoked": c.providers_revoked,
                                "providers_granted": c.providers_granted,
                                "server_success": c.server_success,
                                "server_message": c.server_message,
                            }
                            for c in s.changes
                        ],
                    }
                    for s in self.scan_history
                ],
            }


# Module-level singleton shared between agent and dashboard
state = AgentDashboardState()
