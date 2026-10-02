from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.card import Card


class Transaction(Base):
    """Journal des transactions.

    La contrainte UNIQUE sur `transaction_id` est la garantie ultime d'idempotence.
    `route_id` contient le code de ligne envoyé par le scanner (ex. ROUTE-001).
    `fare` = tarif demandé ; `amount` = montant réellement débité (0 pour un abonnement).
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    vehicle_id: Mapped[str] = mapped_column(String(64))
    route_id: Mapped[str] = mapped_column(String(64))
    fare: Mapped[Decimal] = mapped_column(Numeric(12, 3))
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
