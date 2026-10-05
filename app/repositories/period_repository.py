from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.models.subscription import SubscriptionPeriod


class PeriodRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_by_code(self, code: str) -> SubscriptionPeriod | None:
        return self.db.scalar(
            select(SubscriptionPeriod).where(
                SubscriptionPeriod.code == code, SubscriptionPeriod.status == EntityStatus.ACTIVE.value
            )
        )
