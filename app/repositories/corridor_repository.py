from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.models.corridor import Corridor


class CorridorRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_by_code(self, code: str) -> Corridor | None:
        return self.db.scalar(
            select(Corridor).where(Corridor.code == code, Corridor.status == EntityStatus.ACTIVE.value)
        )
