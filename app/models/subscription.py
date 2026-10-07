from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CategoryType, EntityStatus
from app.models.base import Base

_SUBSCRIPTION_TYPE = CategoryType.SUBSCRIPTION.value


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


class SubscriptionFare(Base):
    """Tarif d'abonnement d'UNE liaison, selon la catégorie et la période, historisé par date de début de validité.
    Configurable en base, indépendant des abonnements. Les lignes de cette table ne sont jamais modifiées : un nouveau
    tarif = une nouvelle ligne avec une nouvelle `valid_from` (les abonnements déjà vendus gardent le tarif d'origine).
    """

    __tablename__ = "subscription_fares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["category_id", "category_type"], ["categories.id", "categories.type"], name="fk_subscription_fares_category"
        ),
        CheckConstraint(f"category_type = '{_SUBSCRIPTION_TYPE}'", name="ck_subscription_fares_category_type"),
        UniqueConstraint("category_id", "corridor_id", "period_id", "valid_from", name="uq_subscription_fares_rule"),
        # cible de la clé étrangère composite de `subscription_corridors` (cohérence période + liaison)
        UniqueConstraint("id", "period_id", "corridor_id", name="uq_subscription_fares_id_period_corridor"),
        CheckConstraint("amount >= 0", name="ck_subscription_fares_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column()
    category_type: Mapped[str] = mapped_column(String(20), default=_SUBSCRIPTION_TYPE, server_default=_SUBSCRIPTION_TYPE)
    corridor_id: Mapped[int] = mapped_column(ForeignKey("corridors.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("subscription_periods.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    valid_from: Mapped[date] = mapped_column(Date)


class Subscription(Base):
    """Abonnement d'une carte : UNE catégorie, UNE période, une validité (dates incluses) et des liaisons.

    Règle de durée : la période est portée par l'abonnement lui-même, jamais par une liaison : un abonnement annuel
    ne contient que des liaisons au tarif annuel, un abonnement semestriel que des liaisons au tarif semestriel.
    Pour mélanger, on crée deux abonnements pour la même carte. `amount` = prix payé (calculé par le service à partir
    des tarifs ; ce n'est pas forcément la simple somme des liaisons : la règle de calcul vit dans le service).
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["category_id", "category_type"], ["categories.id", "categories.type"], name="fk_subscriptions_category"
        ),
        CheckConstraint(f"category_type = '{_SUBSCRIPTION_TYPE}'", name="ck_subscriptions_category_type"),
        CheckConstraint("valid_until >= valid_from", name="ck_subscriptions_dates"),
        CheckConstraint("amount >= 0", name="ck_subscriptions_amount_non_negative"),
        # cible de la clé étrangère composite de `subscription_corridors` (une liaison hérite de la période)
        UniqueConstraint("id", "period_id", name="uq_subscriptions_id_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    category_id: Mapped[int] = mapped_column()
    category_type: Mapped[str] = mapped_column(String(20), default=_SUBSCRIPTION_TYPE, server_default=_SUBSCRIPTION_TYPE)
    period_id: Mapped[int] = mapped_column(ForeignKey("subscription_periods.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    card: Mapped["Card"] = relationship(back_populates="subscriptions")  # noqa: F821
    category: Mapped["Category"] = relationship()  # noqa: F821
    period: Mapped[SubscriptionPeriod] = relationship()
    subscription_corridors: Mapped[list["SubscriptionCorridor"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    @property
    def corridors(self) -> list["Corridor"]:  # noqa: F821
        return [sc.corridor for sc in self.subscription_corridors]


class SubscriptionCorridor(Base):
    """Many-to-Many abonnement <-> liaison, avec le tarif (`fare_id`) appliqué à la souscription.

    Garanties de la base (clés étrangères composites) :
      * (subscription_id, period_id) -> subscriptions(id, period_id) : la période de la liaison est celle de l'abonnement ;
      * (fare_id, period_id, corridor_id) -> subscription_fares(id, period_id, corridor_id) : le tarif utilisé est bien
        celui de CETTE liaison et de CETTE période -> impossible de mélanger annuel et semestriel dans un abonnement.
    `fare_id` est NULL pour une catégorie à gratuité totale (pas de tarif).
    """

    __tablename__ = "subscription_corridors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subscription_id", "period_id"], ["subscriptions.id", "subscriptions.period_id"],
            name="fk_subscription_corridors_subscription_period",
        ),
        ForeignKeyConstraint(
            ["fare_id", "period_id", "corridor_id"],
            ["subscription_fares.id", "subscription_fares.period_id", "subscription_fares.corridor_id"],
            name="fk_subscription_corridors_fare",
        ),
    )

    subscription_id: Mapped[int] = mapped_column(primary_key=True)
    corridor_id: Mapped[int] = mapped_column(ForeignKey("corridors.id"), primary_key=True)
    period_id: Mapped[int] = mapped_column()
    fare_id: Mapped[int | None] = mapped_column(nullable=True)

    subscription: Mapped[Subscription] = relationship(back_populates="subscription_corridors")
    corridor: Mapped["Corridor"] = relationship()  # noqa: F821
