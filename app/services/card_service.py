"""Gestion des cartes : historique par utilisateur, UNE SEULE carte active à la fois.

La règle est vérifiée ici (message clair) ET garantie par l'index unique partiel `uq_cards_one_active_per_user`
en base (filet de sécurité, y compris en cas d'accès concurrents).
Remplacer une carte : `set_status(ancienne, REPLACED)` puis `issue_card(utilisateur, nouveau_tag)`.
"""
import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_CURRENCY, CardStatus
from app.core.exceptions import ActiveCardAlreadyExistsError
from app.models.card import Card
from app.models.user import User
from app.repositories.card_repository import CardRepository


class CardService:
    def __init__(self, db: Session, cards: CardRepository):
        self.db = db
        self.cards = cards

    @classmethod
    def from_session(cls, db: Session) -> "CardService":
        return cls(db, CardRepository(db))

    def issue_card(
        self,
        user: User,
        card_tag: str,
        *,
        status: CardStatus = CardStatus.ACTIVE,
        balance: Decimal = Decimal("0.000"),
    ) -> Card:
        """Associe une nouvelle carte à l'utilisateur (flush, sans commit)."""
        if not re.fullmatch(r"[0-9]{10}", card_tag):
            raise ValueError("card_tag : exactement 10 chiffres")
        if self.cards.get_by_tag(card_tag) is not None:
            raise ValueError(f"La carte {card_tag} existe déjà")
        if status == CardStatus.ACTIVE:
            self._ensure_no_other_active_card(user.id)
        card = Card(
            card_tag=card_tag, user_id=user.id, status=CardStatus(status).value, balance=balance,
            currency=DEFAULT_CURRENCY,
        )
        return self.cards.add(card)

    def set_status(self, card: Card, new_status: CardStatus) -> Card:
        """Change l'état d'une carte. Activer une carte alors que l'utilisateur en a déjà une active est refusé."""
        new_status = CardStatus(new_status)
        if new_status == CardStatus.ACTIVE:
            self._ensure_no_other_active_card(card.user_id, exclude_card_id=card.id)
        card.status = new_status.value
        self.db.flush()
        return card

    def _ensure_no_other_active_card(self, user_id: int, exclude_card_id: int | None = None) -> None:
        active = self.cards.get_active_for_user(user_id, exclude_card_id)
        if active is not None:
            raise ActiveCardAlreadyExistsError(
                f"Cet utilisateur possède déjà une carte active ({active.card_tag})."
            )
