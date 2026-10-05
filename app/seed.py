"""Données de test (idempotent).

Usage :
    python -m app.seed            # crée ce qui manque (lignes, tarifs, catégories, périodes, utilisateurs, cartes, abonnements)
    python -m app.seed --reset    # remet soldes/états des cartes de test à l'état initial et purge les transactions

Voir app/data/sts_lines.py (lignes, tarifs au trajet) et app/data/subscription_catalog.py (catégories, périodes, tarifs d'abonnement).
"""
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import CardStatus, EntityStatus
from app.data.sts_lines import LINE_FARES, STS_LINES
from app.data.subscription_catalog import CATEGORIES, PERIODS, SUBSCRIPTION_TARIFFS
from app.dependencies.database import SessionLocal
from app.models import (
    Card,
    Category,
    Line,
    LineFare,
    Subscription,
    SubscriptionPeriod,
    SubscriptionTariff,
    Transaction,
    User,
)
from app.services.card_service import CardService
from app.services.subscription_service import SubscriptionService
from app.services.user_service import UserService

START_2026 = date(2026, 1, 1)
START_2025 = date(2025, 1, 1)

# Utilisateurs nommés (les autres cartes reçoivent un utilisateur « Utilisateur Test <carte> »)
USERS = {
    "ahmad": ("Ahmad", "Test"),
    "rim": ("Rim", "Test"),
    "handicap": ("Utilisateur", "Handicapé Test"),
}

# (card_tag, utilisateur, état, solde, [(catégorie, période, début, [numéros de lignes])])
# Un utilisateur peut avoir plusieurs cartes (historique) mais une seule ACTIVE.
CARDS: list[tuple[str, str | None, CardStatus, str, list[tuple[str, str, date, list[str]]]]] = [
    ("1000000001", None, CardStatus.ACTIVE, "10.000", [("PASSENGER", "ANNUAL", START_2026, ["22A", "52A", "61"])]),
    ("1000000002", None, CardStatus.ACTIVE, "0.300", []),
    ("1000000003", None, CardStatus.ACTIVE, "10.000", []),
    ("1000000004", None, CardStatus.BLOCKED, "10.000", []),
    ("1000000005", None, CardStatus.ACTIVE, "10.000", [("PASSENGER", "ANNUAL", START_2026, ["61"])]),
    ("1000000006", None, CardStatus.EXPIRED, "10.000", []),
    ("1000000007", None, CardStatus.ACTIVE, "10.000", [("PASSENGER", "ANNUAL", START_2025, ["22A"])]),  # périmé fin 2025
    ("1000000008", "handicap", CardStatus.ACTIVE, "10.000", [("DISABLED", "ANNUAL", START_2026, [])]),
    # Historique de cartes d'une même utilisatrice : perdue, remplacée, puis la carte active
    ("1000000009", "rim", CardStatus.LOST, "10.000", []),
    ("1000000010", "rim", CardStatus.REPLACED, "10.000", []),
    ("1000000011", "rim", CardStatus.ACTIVE, "10.000", []),
    ("1000000012", None, CardStatus.INACTIVE, "10.000", []),
    # Exemple de l'énoncé : une carte, deux abonnements (catégories et lignes différentes)
    ("1236547895", "ahmad", CardStatus.ACTIVE, "10.000", [
        ("UNIVERSITY", "ANNUAL", START_2026, ["13C", "16"]),
        ("PASSENGER", "ANNUAL", START_2026, ["52A"]),
    ]),
    # Scénario « deux bus »
    ("1258465854", None, CardStatus.ACTIVE, "10.000", []),
    ("1258465855", None, CardStatus.ACTIVE, "10.000", []),
]


def seed(db: Session, reset: bool = False) -> None:
    if reset:
        db.execute(delete(Transaction))

    # --- lignes et tarifs au trajet
    lines: dict[str, Line] = {}
    for number, departure, destination, via in STS_LINES:
        line = db.scalar(select(Line).where(Line.number == number))
        if line is None:
            line = Line(number=number, departure=departure, destination=destination, via=via,
                        status=EntityStatus.ACTIVE.value)
            db.add(line)
        lines[number] = line
    db.flush()
    for number, amount, valid_from in LINE_FARES:
        if db.scalar(select(LineFare.id).where(LineFare.line_id == lines[number].id,
                                                LineFare.valid_from == valid_from)) is None:
            db.add(LineFare(line_id=lines[number].id, amount=Decimal(amount), valid_from=valid_from))
    db.flush()

    # --- catégories, périodes, tarifs d'abonnement
    categories: dict[str, Category] = {}
    for code, name, free_travel in CATEGORIES:
        category = db.scalar(select(Category).where(Category.code == code))
        if category is None:
            category = Category(code=code, name=name, free_travel=free_travel, status=EntityStatus.ACTIVE.value)
            db.add(category)
        categories[code] = category
    periods: dict[str, SubscriptionPeriod] = {}
    for code, name, months in PERIODS:
        period = db.scalar(select(SubscriptionPeriod).where(SubscriptionPeriod.code == code))
        if period is None:
            period = SubscriptionPeriod(code=code, name=name, months=months, status=EntityStatus.ACTIVE.value)
            db.add(period)
        periods[code] = period
    db.flush()
    for number, cat_code, period_code, amount, valid_from in SUBSCRIPTION_TARIFFS:
        exists = db.scalar(
            select(SubscriptionTariff.id).where(
                SubscriptionTariff.category_id == categories[cat_code].id,
                SubscriptionTariff.line_id == lines[number].id,
                SubscriptionTariff.period_id == periods[period_code].id,
                SubscriptionTariff.valid_from == valid_from,
            )
        )
        if exists is None:
            db.add(SubscriptionTariff(
                category_id=categories[cat_code].id, line_id=lines[number].id, period_id=periods[period_code].id,
                amount=Decimal(amount), valid_from=valid_from,
            ))
    db.flush()

    # --- utilisateurs, cartes, abonnements
    user_service = UserService.from_session(db)
    card_service = CardService.from_session(db)
    subscription_service = SubscriptionService.from_session(db)

    for tag, user_key, status, balance, subscriptions in CARDS:
        first_name, last_name = USERS.get(user_key or "", ("Utilisateur", f"Test {tag}"))
        user = db.scalar(select(User).where(User.first_name == first_name, User.last_name == last_name))
        if user is None:
            user = user_service.create_user(first_name, last_name)
        card = db.scalar(select(Card).where(Card.card_tag == tag))
        if card is None:
            card = card_service.issue_card(user, tag, status=status, balance=Decimal(balance))
        elif reset:
            card.status = status.value
            card.balance = Decimal(balance)
            db.flush()
        for cat_code, period_code, start, line_numbers in subscriptions:
            exists = db.scalar(
                select(Subscription.id).where(
                    Subscription.card_id == card.id,
                    Subscription.category_id == categories[cat_code].id,
                    Subscription.period_id == periods[period_code].id,
                    Subscription.valid_from == start,
                )
            )
            if exists is None:
                subscription_service.create_subscription(card, cat_code, period_code, line_numbers, start)
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session, reset="--reset" in sys.argv)
    print("Données de test réinitialisées." if "--reset" in sys.argv else "Données de test prêtes.")
