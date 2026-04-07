"""Persists the last-known employee snapshot to a local JSON file."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connectors.base import EmployeeRecord

logger = logging.getLogger(__name__)

# email → {"name", "role", "status"}
EmployeeSnapshot = dict[str, dict]


def load_state(path: str) -> EmployeeSnapshot:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read state file %s: %s", path, exc)
        return {}


def save_state(path: str, employees: list[EmployeeRecord]) -> None:
    snapshot: EmployeeSnapshot = {
        e.email: {"name": e.name, "role": e.role, "status": e.status}
        for e in employees
    }
    try:
        Path(path).write_text(json.dumps(snapshot, indent=2))
    except OSError as exc:
        logger.error("Could not write state file %s: %s", path, exc)


def diff_snapshots(
    previous: EmployeeSnapshot,
    current: list[EmployeeRecord],
) -> list[dict]:
    """
    Compare previous snapshot to current records and return a list of change dicts:
        {email, name, action_type, previous_role, new_role}
    """
    changes: list[dict] = []
    current_map: EmployeeSnapshot = {
        e.email: {"name": e.name, "role": e.role, "status": e.status}
        for e in current
    }

    # Detect new employees and role changes
    for email, cur in current_map.items():
        prev = previous.get(email)

        if prev is None:
            if cur["status"] == "active":
                changes.append({
                    "email": email,
                    "name": cur["name"],
                    "action_type": "added",
                    "previous_role": None,
                    "new_role": cur["role"],
                })
        elif prev["status"] != "left" and cur["status"] == "left":
            changes.append({
                "email": email,
                "name": cur["name"],
                "action_type": "terminated",
                "previous_role": prev["role"],
                "new_role": None,
            })
        elif prev["status"] == "active" and cur["status"] == "active" and prev["role"] != cur["role"]:
            changes.append({
                "email": email,
                "name": cur["name"],
                "action_type": "role_changed",
                "previous_role": prev["role"],
                "new_role": cur["role"],
            })

    return changes
