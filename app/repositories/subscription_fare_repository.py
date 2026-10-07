from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subscription import SubscriptionFare


class SubscriptionFareRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_applicable(self, category_id: int, corridor_id: int, period_id: int, on_date: date) -> SubscriptionFare | None:
        """Tarif d'abonnement de la combinaison catégorie + liaison + période applicable à `on_date`
        (le plus récent dont la date de début de validité est <= `on_date`), ou None."""
        stmt = (
            select(SubscriptionFare)
            .where(
                SubscriptionFare.category_id == category_id,
                SubscriptionFare.corridor_id == corridor_id,
                SubscriptionFare.period_id == period_id,
                SubscriptionFare.valid_from <= on_date,
            )
            .order_by(SubscriptionFare.valid_from.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)
