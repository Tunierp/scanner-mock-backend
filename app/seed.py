"""Données de test (idempotent).

Usage :
    python -m app.seed            # crée ce qui manque
    python -m app.seed --reset    # remet soldes/statuts à l'état initial et purge les transactions
"""
import sys
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import CardStatus, EntityStatus
from app.dependencies.database import SessionLocal
from app.models import (
    Card,
    CardSubscription,
    Route,
    Subscription,
    SubscriptionRoute,
    Transaction,
)

VALID_FROM = datetime(2026, 1, 1, tzinfo=UTC)
VALID_UNTIL = datetime(2036, 12, 31, 23, 59, 59, tzinfo=UTC)
EXPIRED_UNTIL = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)

ROUTES = {"ROUTE-001": "Ligne 1", "ROUTE-002": "Ligne 2", "ROUTE-003": "Ligne 3"}

SUBSCRIPTIONS = {
    "SUB-001": ("Abonnement ligne 1", ["ROUTE-001"]),
    "SUB-002": ("Abonnement ligne 3", ["ROUTE-003"]),
    "SUB-EXPIRED": ("Abonnement ligne 1 (périmé)", ["ROUTE-001"]),
}

# (card_token, status, balance, [(subscription_name, valid_from, valid_until)])
CARDS = [
    ("CARD-TEST-001", CardStatus.ACTIVE, "10.000", [("SUB-001", VALID_FROM, VALID_UNTIL)]),
    ("CARD-TEST-002", CardStatus.ACTIVE, "0.300", []),
    ("CARD-TEST-003", CardStatus.ACTIVE, "10.000", []),
    ("CARD-TEST-004", CardStatus.BLOCKED, "10.000", []),
    ("CARD-TEST-005", CardStatus.ACTIVE, "10.000", [("SUB-002", VALID_FROM, VALID_UNTIL)]),
    ("CARD-TEST-006", CardStatus.EXPIRED, "10.000", []),
    ("CARD-TEST-007", CardStatus.ACTIVE, "10.000", [("SUB-EXPIRED", VALID_FROM, EXPIRED_UNTIL)]),
]


def seed(db: Session, reset: bool = False) -> None:
    if reset:
        db.execute(delete(Transaction))

    routes: dict[str, Route] = {}
    for code, name in ROUTES.items():
        route = db.scalar(select(Route).where(Route.code == code))
        if route is None:
            route = Route(code=code, name=name, status=EntityStatus.ACTIVE.value)
            db.add(route)
        routes[code] = route
    db.flush()

    subscriptions: dict[str, Subscription] = {}
    for name, (description, route_codes) in SUBSCRIPTIONS.items():
        subscription = db.scalar(select(Subscription).where(Subscription.name == name))
        if subscription is None:
            subscription = Subscription(name=name, description=description, status=EntityStatus.ACTIVE.value)
            db.add(subscription)
            db.flush()
        for code in route_codes:
            link = db.scalar(
                select(SubscriptionRoute).where(
                    SubscriptionRoute.subscription_id == subscription.id,
                    SubscriptionRoute.route_id == routes[code].id,
                )
            )
            if link is None:
                db.add(SubscriptionRoute(subscription_id=subscription.id, route_id=routes[code].id))
        subscriptions[name] = subscription
    db.flush()

    for token, status, balance, subs in CARDS:
        card = db.scalar(select(Card).where(Card.card_token == token))
        if card is None:
            card = Card(card_token=token, status=status.value, balance=Decimal(balance), currency="TND")
            db.add(card)
            db.flush()
        elif reset:
            card.status = status.value
            card.balance = Decimal(balance)
        for sub_name, valid_from, valid_until in subs:
            card_sub = db.scalar(
                select(CardSubscription).where(
                    CardSubscription.card_id == card.id,
                    CardSubscription.subscription_id == subscriptions[sub_name].id,
                )
            )
            if card_sub is None:
                db.add(
                    CardSubscription(
                        card_id=card.id,
                        subscription_id=subscriptions[sub_name].id,
                        valid_from=valid_from,
                        valid_until=valid_until,
                        status=EntityStatus.ACTIVE.value,
                    )
                )
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session, reset="--reset" in sys.argv)
    print("Données de test prêtes." if "--reset" not in sys.argv else "Données de test réinitialisées.")
