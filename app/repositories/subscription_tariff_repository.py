from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subscription import SubscriptionTariff


class SubscriptionTariffRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_applicable(self, category_id: int, line_id: int, period_id: int, on_date: date) -> Decimal | None:
        """Tarif d'abonnement de la combinaison catégorie + ligne + période applicable à `on_date`
        (le plus récent dont la date de début de validité est <= `on_date`), ou None."""
        stmt = (
            select(SubscriptionTariff.amount)
            .where(
                SubscriptionTariff.category_id == category_id,
                SubscriptionTariff.line_id == line_id,
                SubscriptionTariff.period_id == period_id,
                SubscriptionTariff.valid_from <= on_date,
            )
            .order_by(SubscriptionTariff.valid_from.desc())
            .limit(1)
        )
        amount = self.db.scalar(stmt)
        return None if amount is None else Decimal(amount).quantize(Decimal("0.001"))
