from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.card import Card


class CardRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_token(self, card_token: str, *, for_update: bool = False) -> Card | None:
        """Retourne la carte. Avec `for_update=True` : SELECT ... FOR UPDATE (verrou de ligne).

        `populate_existing` garantit que le solde lu est celui de la base (et non un objet périmé
        de la session) une fois le verrou obtenu.
        """
        stmt = select(Card).where(Card.card_token == card_token)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.db.scalar(stmt)

    def set_balance(self, card: Card, new_balance: Decimal) -> None:
        card.balance = new_balance
        self.db.flush()
