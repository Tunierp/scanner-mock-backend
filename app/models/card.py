from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CardStatus
from app.models.base import Base


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_cards_balance_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    card_tag: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=CardStatus.ACTIVE.value)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0.000"))
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscriptions: Mapped[list["CardSubscription"]] = relationship(back_populates="card")  # noqa: F821
