from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.models.line import Line


class LineRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_by_number(self, number: str) -> Line | None:
        stmt = select(Line).where(Line.number == number, Line.status == EntityStatus.ACTIVE.value)
        return self.db.scalar(stmt)
