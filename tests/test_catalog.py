"""Lignes, tarifs au trajet, catégories, périodes, tarifs d'abonnement : données chargées et extensibilité."""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.dependencies.database import SessionLocal
from app.models import (
    Card, Category, Line, LineFare, Subscription, SubscriptionPeriod, SubscriptionTariff, User,
)
from tests.conftest import CARD_AHMAD, CARD_OK, CARD_SUB, PAYMENTS_URL, payment_payload


def test_sts_lines_are_loaded_with_departure_and_destination():
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Line.id))) == 29
        line = db.scalar(select(Line).where(Line.number == "22A"))
        assert (line.departure, line.destination) == ("Sousse", "Msaken")
        assert line.label == "22A - Sousse - Msaken"
        assert db.scalar(select(Line.via).where(Line.number == "60")) == "Masdour - Jammel"


def test_line_fares_are_historized_by_start_date():
    with SessionLocal() as db:
        line = db.scalar(select(Line).where(Line.number == "22A"))
        assert [(f.valid_from, f.amount) for f in line.fares] == [
            (date(2023, 5, 12), Decimal("1.100")),
            (date(2025, 1, 1), Decimal("1.200")),
        ]


def test_categories_and_periods_are_loaded():
    with SessionLocal() as db:
        categories = {c.code: c for c in db.scalars(select(Category))}
        assert set(categories) == {"UNIVERSITY", "SCHOOL", "DISABLED", "PASSENGER", "WORKER", "INTERN"}
        assert [code for code, c in categories.items() if c.free_travel] == ["DISABLED"]
        periods = {p.code: p.months for p in db.scalars(select(SubscriptionPeriod))}
        assert periods == {"MONTHLY": 1, "QUARTERLY": 3, "SEMIANNUAL": 6, "ANNUAL": 12}


def test_relations_user_card_subscription_category_lines():
    """Utilisateur → Carte → Abonnements → Catégorie + Lignes (exemple d'Ahmad)."""
    with SessionLocal() as db:
        card = db.scalar(select(Card).where(Card.card_tag == CARD_AHMAD))
        assert card.user.first_name == "Ahmad"
        subs = sorted(card.subscriptions, key=lambda s: s.category.code)
        assert [(s.category.name, s.period.code, sorted(l.number for l in s.lines)) for s in subs] == [
            ("Passager", "ANNUAL", ["52A"]),
            ("Universitaire", "ANNUAL", ["13C", "16"]),
        ]
        assert [s.total_price for s in subs] == [Decimal("30.000"), Decimal("42.000")]
        assert [(s.valid_from, s.valid_until) for s in subs] == [(date(2026, 1, 1), date(2026, 12, 31))] * 2


def test_a_line_is_present_in_several_subscriptions():
    with SessionLocal() as db:
        line_61 = db.scalar(select(Line).where(Line.number == "61"))
        assert len(line_61.subscription_lines) >= 2


def test_a_user_can_have_several_cards_in_history_but_one_active():
    with SessionLocal() as db:
        rim = db.scalar(select(User).where(User.first_name == "Rim"))
        assert sorted(c.status for c in rim.cards) == ["ACTIVE", "LOST", "REPLACED"]


def test_a_new_line_and_a_new_fare_can_be_added_without_code_change(client):
    with SessionLocal() as db:
        line = Line(number="99Z", departure="Sousse", destination="Test", via=None, status="ACTIVE")
        db.add(line)
        db.flush()
        db.add(LineFare(line_id=line.id, amount=Decimal("2.000"), valid_from=date(2026, 1, 1)))
        db.commit()
    data = client.post(PAYMENTS_URL, json=payment_payload(card_tag=CARD_OK, line_number="99Z")).json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert data["amount"] == 2.0


def test_a_new_fare_for_an_existing_line_takes_over_from_its_start_date(client):
    with SessionLocal() as db:
        line = db.scalar(select(Line).where(Line.number == "22A"))
        db.add(LineFare(line_id=line.id, amount=Decimal("1.500"), valid_from=date(2026, 9, 1)))
        db.commit()
    assert client.post(PAYMENTS_URL, json=payment_payload(card_tag=CARD_OK)).json()["data"]["amount"] == 1.5
    old = client.post(
        PAYMENTS_URL, json=payment_payload(transaction_id="OLD", card_tag=CARD_OK, occurred_at="2026-08-15T10:00:00Z")
    ).json()["data"]
    assert old["amount"] == 1.2


def test_seed_is_idempotent_and_keeps_data():
    from app.seed import seed

    with SessionLocal() as db:
        seed(db)
        seed(db)
        assert db.scalar(select(func.count(Card.id))) == 15
        assert db.scalar(select(func.count(Subscription.id))) == 6
        assert db.scalar(select(func.count(SubscriptionTariff.id))) == 6


def test_card_sub_has_the_three_lines_of_its_subscription():
    with SessionLocal() as db:
        card = db.scalar(select(Card).where(Card.card_tag == CARD_SUB))
        (sub,) = card.subscriptions
        assert sorted(l.number for l in sub.lines) == ["22A", "52A", "61"]
        assert sub.total_price == Decimal("86.000")  # 31.000 + 30.000 + 25.000
