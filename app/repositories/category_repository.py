from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CategoryType, EntityStatus
from app.models.category import Category


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_by_code(self, code: str, category_type: CategoryType = CategoryType.SUBSCRIPTION) -> Category | None:
        """Les codes ne sont uniques que PAR TYPE : on précise toujours le type de catégorie cherché."""
        return self.db.scalar(
            select(Category).where(
                Category.type == CategoryType(category_type).value,
                Category.code == code,
                Category.status == EntityStatus.ACTIVE.value,
            )
        )
