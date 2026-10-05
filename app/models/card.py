from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CardStatus
from app.models.base import Base


class Card(Base):
    """Carte d'un utilisateur. Un utilisateur peut en avoir plusieurs dans son historique (perdue, remplacée,
    expirée...) mais UNE SEULE ACTIVE : garanti par l'index unique partiel `uq_cards_one_active_per_user`."""

    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_cards_balance_non_negative"),
        Index(
            "uq_cards_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    card_tag: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=CardStatus.ACTIVE.value)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0.000"))
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="cards")  # noqa: F821
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="card")  # noqa: F821
