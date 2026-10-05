from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CardStatus
from app.models.card import Card


class CardRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_tag(self, card_tag: str, *, for_update: bool = False) -> Card | None:
        """Retourne la carte. Avec `for_update=True` : SELECT ... FOR UPDATE (verrou de ligne).

        `populate_existing` garantit que le solde lu est celui de la base (et non un objet périmé
        de la session) une fois le verrou obtenu.
        """
        stmt = select(Card).where(Card.card_tag == card_tag)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.db.scalar(stmt)

    def set_balance(self, card: Card, new_balance: Decimal) -> None:
        card.balance = new_balance
        self.db.flush()

    def get_active_for_user(self, user_id: int, exclude_card_id: int | None = None) -> Card | None:
        """Carte ACTIVE de l'utilisateur (il n'en a qu'une au plus), hors `exclude_card_id`."""
        stmt = select(Card).where(Card.user_id == user_id, Card.status == CardStatus.ACTIVE.value)
        if exclude_card_id is not None:
            stmt = stmt.where(Card.id != exclude_card_id)
        return self.db.scalar(stmt)

    def add(self, card: Card) -> Card:
        self.db.add(card)
        self.db.flush()
        return card
