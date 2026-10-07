"""⚠ TEMPORAIRE — réinitialisation des données de test (équivalent de `python -m app.seed --reset`).

À supprimer avec `app/routers/data_reset.py` et `app/schemas/data_reset.py` (voir README).
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Card, Transaction
from app.seed import CARDS, seed

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CardState:
    card_tag: str
    status: str
    balance: Decimal


@dataclass(frozen=True)
class ResetResult:
    deleted_transactions: int
    cards: list[CardState]


class DataResetService:
    def __init__(self, db: Session):
        self.db = db

    def reset(self) -> ResetResult:
        """Supprime TOUTES les transactions, remet les cartes de test (solde et état) à leur état initial et recrée ce
        qui manque des données de test. Les données ajoutées en dehors du seed (lignes, tarifs...) sont conservées.
        Tout se fait dans une seule transaction : en cas d'erreur, rien n'est modifié."""
        deleted = self.db.scalar(select(func.count(Transaction.id))) or 0
        try:
            seed(self.db, reset=True)  # valide la transaction (commit) à la fin
        except Exception:
            self.db.rollback()
            raise
        tags = [tag for tag, *_ in CARDS]
        cards = self.db.scalars(select(Card).where(Card.card_tag.in_(tags)).order_by(Card.card_tag))
        logger.warning("Données de test réinitialisées : %s transaction(s) supprimée(s)", deleted)
        return ResetResult(deleted, [CardState(c.card_tag, c.status, Decimal(c.balance)) for c in cards])
