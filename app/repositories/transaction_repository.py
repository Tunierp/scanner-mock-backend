from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_transaction_id(self, transaction_id: str) -> Transaction | None:
        return self.db.scalar(select(Transaction).where(Transaction.transaction_id == transaction_id))

    def add(self, transaction: Transaction) -> Transaction:
        """Insère et flush immédiatement : la contrainte UNIQUE est évaluée ici (IntegrityError)."""
        self.db.add(transaction)
        self.db.flush()
        return transaction
