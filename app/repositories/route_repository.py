from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.models.route import Route


class RouteRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_by_code(self, code: str) -> Route | None:
        stmt = select(Route).where(Route.code == code, Route.status == EntityStatus.ACTIVE.value)
        return self.db.scalar(stmt)
