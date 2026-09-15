from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import Admin, LabUser, ProvisioningRecord, UserStatus
from app.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    counts = dict(
        db.query(LabUser.status, func.count(LabUser.id)).group_by(LabUser.status).all()
    )

    def c(s: UserStatus) -> int:
        return counts.get(s, 0)

    soon_threshold = datetime.utcnow() + timedelta(days=7)
    expiring_soon = (
        db.query(func.count(LabUser.id))
        .filter(LabUser.status == UserStatus.ACTIVE)
        .filter(LabUser.expires_at <= soon_threshold)
        .scalar()
    )

    env_rows = (
        db.query(ProvisioningRecord.environment, ProvisioningRecord.status, func.count(ProvisioningRecord.id))
        .group_by(ProvisioningRecord.environment, ProvisioningRecord.status)
        .all()
    )
    by_env: dict[str, dict[str, int]] = {}
    for environment, status_value, count in env_rows:
        by_env.setdefault(environment.value, {})[status_value.value] = count

    total = db.query(func.count(LabUser.id)).scalar()

    return DashboardStats(
        total_users=total,
        active_users=c(UserStatus.ACTIVE),
        pending_users=c(UserStatus.PENDING),
        revoked_users=c(UserStatus.REVOKED),
        purged_users=c(UserStatus.PURGED),
        failed_users=c(UserStatus.FAILED),
        expiring_in_7_days=expiring_soon or 0,
        users_by_environment_status=by_env,
    )
