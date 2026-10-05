from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.models.category import Category


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_by_code(self, code: str) -> Category | None:
        return self.db.scalar(
            select(Category).where(Category.code == code, Category.status == EntityStatus.ACTIVE.value)
        )
