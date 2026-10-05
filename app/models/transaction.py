from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.card import Card
from app.models.line import Line


class Transaction(Base):
    """Journal des transactions.

    L'identité d'un scan est (device_id, transaction_id, occurred_at) : la contrainte UNIQUE correspondante est la
    garantie ultime d'idempotence. Un `transaction_id` réutilisé un autre jour (compteur remis à zéro, par
    exemple) n'est donc PAS pris pour un renvoi : l'heure du badge (`occurred_at`) est différente.
    `fare` = tarif (un sens) applicable à la date du scan, NULL si aucun tarif n'est défini ;
    `amount` = montant réellement débité (0 pour un abonnement).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("device_id", "transaction_id", "occurred_at", name="uq_transactions_scan"),
        Index("ix_transactions_trip_lookup", "card_id", "vehicle_id", "line_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64))
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    vehicle_id: Mapped[str] = mapped_column(String(64))
    line_id: Mapped[int] = mapped_column(ForeignKey("lines.id"))
    fare: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    currency: Mapped[str] = mapped_column(String(3))
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    balance_before: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    card: Mapped[Card] = relationship()
    line: Mapped[Line] = relationship()
