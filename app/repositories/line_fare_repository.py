from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.line import LineFare


class LineFareRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_applicable(self, line_id: int, on_date: date) -> Decimal | None:
        """Tarif (un sens) applicable à `on_date` : le plus récent dont la date de début de validité
        est <= `on_date`. None si la ligne n'a pas de tarif à cette date."""
        stmt = (
            select(LineFare.amount)
            .where(LineFare.line_id == line_id, LineFare.valid_from <= on_date)
            .order_by(LineFare.valid_from.desc())
            .limit(1)
        )
        amount = self.db.scalar(stmt)
        return None if amount is None else Decimal(amount).quantize(Decimal("0.001"))
