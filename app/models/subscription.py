from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EntityStatus
from app.models.base import Base


class SubscriptionPeriod(Base):
    """Période d'abonnement (Mensuel, Trimestriel, Semestriel, Annuel...). Extensible : une période = une ligne
    avec sa durée en mois."""

    __tablename__ = "subscription_periods"
    __table_args__ = (CheckConstraint("months > 0", name="ck_subscription_periods_months_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    months: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)


class SubscriptionTariff(Base):
    """Tarif d'abonnement pour UNE ligne, selon la catégorie et la période, historisé par date de début de
    validité. Configurable en base, indépendant des abonnements (qui en gardent une copie du prix)."""

    __tablename__ = "subscription_tariffs"
    __table_args__ = (
        UniqueConstraint("category_id", "line_id", "period_id", "valid_from", name="uq_subscription_tariffs_rule"),
        CheckConstraint("amount >= 0", name="ck_subscription_tariffs_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    line_id: Mapped[int] = mapped_column(ForeignKey("lines.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("subscription_periods.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    valid_from: Mapped[date] = mapped_column(Date)


class Subscription(Base):
    """Abonnement d'une carte : une catégorie, une période, une durée de validité (dates incluses) et des lignes.

    Prix total = somme des prix des lignes (`SubscriptionLine.price`, tarif figé à la souscription).
    """

    __tablename__ = "subscriptions"
    __table_args__ = (CheckConstraint("valid_until >= valid_from", name="ck_subscriptions_dates"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("subscription_periods.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    card: Mapped["Card"] = relationship(back_populates="subscriptions")  # noqa: F821
    category: Mapped["Category"] = relationship()  # noqa: F821
    period: Mapped[SubscriptionPeriod] = relationship()
    subscription_lines: Mapped[list["SubscriptionLine"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    @property
    def lines(self) -> list["Line"]:  # noqa: F821
        return [sl.line for sl in self.subscription_lines]

    @property
    def total_price(self) -> Decimal:
        return sum((sl.price for sl in self.subscription_lines), Decimal("0.000")).quantize(Decimal("0.001"))


class SubscriptionLine(Base):
    """Relation Many-to-Many Abonnement <-> Ligne, avec le prix de la ligne dans cet abonnement."""

    __tablename__ = "subscription_lines"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_subscription_lines_price_non_negative"),)

    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("lines.id"), primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 3))

    subscription: Mapped[Subscription] = relationship(back_populates="subscription_lines")
    line: Mapped["Line"] = relationship(back_populates="subscription_lines")  # noqa: F821
