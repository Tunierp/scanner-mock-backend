from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import TransactionStatus
from app.models.transaction import Transaction


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_scan(self, device_id: str, transaction_id: str, occurred_at: datetime) -> Transaction | None:
        """Retrouve un scan déjà traité : même scanner, même transaction_id ET même heure de badge.

        Un renvoi (retry) porte toujours l'heure d'origine du badge ; un autre jour = un autre scan."""
        stmt = select(Transaction).where(
            Transaction.device_id == device_id,
            Transaction.transaction_id == transaction_id,
            Transaction.occurred_at == occurred_at,
        )
        return self.db.scalar(stmt)

    def find_approved_trip_scan(
        self, card_id: int, vehicle_id: str, route_id: str, at: datetime, window: timedelta
    ) -> Transaction | None:
        """Cherche un scan APPROVED de la même carte, dans le même véhicule, sur la même ligne,
        dans la fenêtre [at - window, at + window] (symétrique : l'ordre d'arrivée n'a pas d'importance)."""
        stmt = (
            select(Transaction)
            .where(
                Transaction.card_id == card_id,
                Transaction.vehicle_id == vehicle_id,
                Transaction.route_id == route_id,
                Transaction.status == TransactionStatus.APPROVED.value,
                Transaction.occurred_at >= at - window,
                Transaction.occurred_at <= at + window,
            )
            .limit(1)
        )
        return self.db.scalar(stmt)

    def add(self, transaction: Transaction) -> Transaction:
        """Insère et flush immédiatement : la contrainte UNIQUE est évaluée ici (IntegrityError)."""
        self.db.add(transaction)
        self.db.flush()
        return transaction
