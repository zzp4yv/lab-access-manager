from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    db: Session,
    actor: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=json.dumps(details, default=str) if details else None,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry
