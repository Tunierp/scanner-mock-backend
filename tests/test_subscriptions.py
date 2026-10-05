"""Abonnements : catégories, périodes, tarifs configurables, prix = somme des lignes, validité."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    CategoryNotFoundError, InvalidLineError, PeriodNotFoundError, SubscriptionTariffNotFoundError,
)
from app.dependencies.database import SessionLocal
from app.models import Category, Line, SubscriptionPeriod, SubscriptionTariff
from app.services.card_service import CardService
from app.services.subscription_service import SubscriptionService, add_months, end_of_period
from app.services.user_service import UserService
from tests.conftest import PAYMENTS_URL, payment_payload

START = date(2026, 1, 1)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _id(db, model, **where):
    return db.scalar(select(model.id).filter_by(**where))


def add_tariff(db, line, category, period, amount, valid_from=date(2025, 1, 1)):
    db.add(SubscriptionTariff(
        category_id=_id(db, Category, code=category), line_id=_id(db, Line, number=line),
        period_id=_id(db, SubscriptionPeriod, code=period), amount=Decimal(amount), valid_from=valid_from,
    ))
    db.flush()


@pytest.fixture
def hammam(db):
    """La ligne « Sousse - Hammam Sousse » de l'énoncé, avec ses tarifs Passager : 30.000 / an, 15.000 / semestre.
    (22A, Sousse - Msaken, a déjà 31.000 / an et 16.000 / semestre dans les données de test.)"""
    db.add(Line(number="HS", departure="Sousse", destination="Hammam Sousse", status="ACTIVE"))
    db.flush()
    add_tariff(db, "HS", "PASSENGER", "ANNUAL", "30.000")
    add_tariff(db, "HS", "PASSENGER", "SEMIANNUAL", "15.000")
    return "HS"


# ---------------------------------------------------------------- prix = somme des tarifs des lignes

def test_annual_price_is_the_sum_of_the_line_tariffs(db, hammam):
    quote = SubscriptionService.from_session(db).quote("PASSENGER", "ANNUAL", ["22A", "HS"], START)
    assert [(q.line.number, q.price) for q in quote.lines] == [("22A", Decimal("31.000")), ("HS", Decimal("30.000"))]
    assert quote.total == Decimal("61.000")  # 31.000 + 30.000


def test_semiannual_price_uses_the_semiannual_tariffs(db, hammam):
    quote = SubscriptionService.from_session(db).quote("PASSENGER", "SEMIANNUAL", ["22A", "HS"], START)
    assert quote.total == Decimal("31.000")  # 16.000 + 15.000


def test_the_tariff_depends_on_the_category(db, hammam):
    add_tariff(db, "22A", "UNIVERSITY", "ANNUAL", "20.000")
    add_tariff(db, "HS", "UNIVERSITY", "ANNUAL", "18.000")
    service = SubscriptionService.from_session(db)
    assert service.quote("PASSENGER", "ANNUAL", ["22A", "HS"], START).total == Decimal("61.000")
    assert service.quote("UNIVERSITY", "ANNUAL", ["22A", "HS"], START).total == Decimal("38.000")


def test_the_tariff_is_historized_by_start_date(db):
    add_tariff(db, "22A", "PASSENGER", "ANNUAL", "33.000", valid_from=date(2026, 6, 1))
    service = SubscriptionService.from_session(db)
    assert service.quote("PASSENGER", "ANNUAL", ["22A"], date(2026, 5, 31)).total == Decimal("31.000")
    assert service.quote("PASSENGER", "ANNUAL", ["22A"], date(2026, 6, 1)).total == Decimal("33.000")


def test_missing_tariff_is_an_error_not_a_zero_price(db):
    with pytest.raises(SubscriptionTariffNotFoundError):
        SubscriptionService.from_session(db).quote("PASSENGER", "MONTHLY", ["22A"], START)  # pas de tarif mensuel


def test_a_line_listed_twice_is_counted_once(db):
    assert SubscriptionService.from_session(db).quote("PASSENGER", "ANNUAL", ["22A", "22A"], START).total == Decimal("31.000")


# ---------------------------------------------------------------- catégorie à gratuité totale

def test_disabled_category_is_free_on_all_lines_whatever_the_tariffs(db):
    quote = SubscriptionService.from_session(db).quote("DISABLED", "ANNUAL", ["22A", "28", "60"], START)
    assert quote.total == Decimal("0.000")
    assert all(q.price == Decimal("0.000") for q in quote.lines)


def test_disabled_subscription_may_have_no_line_but_others_need_one(db):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    card = CardService.from_session(db).issue_card(user, "2000000001")
    service = SubscriptionService.from_session(db)
    assert service.create_subscription(card, "DISABLED", "ANNUAL", [], START).total_price == Decimal("0.000")
    with pytest.raises(InvalidLineError):
        service.create_subscription(card, "PASSENGER", "ANNUAL", [], START)


# ---------------------------------------------------------------- création, durée, prix figé

def _card(db, tag="2000000001"):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    return CardService.from_session(db).issue_card(user, tag)


@pytest.mark.parametrize(
    "period, start, expected_end",
    [
        ("MONTHLY", date(2026, 1, 1), date(2026, 1, 31)),
        ("QUARTERLY", date(2026, 1, 1), date(2026, 3, 31)),
        ("SEMIANNUAL", date(2026, 1, 1), date(2026, 6, 30)),
        ("ANNUAL", date(2026, 1, 1), date(2026, 12, 31)),
        ("ANNUAL", date(2026, 9, 15), date(2027, 9, 14)),
        ("MONTHLY", date(2026, 1, 31), date(2026, 2, 27)),
    ],
)
def test_validity_period_comes_from_the_subscription_period(db, period, start, expected_end):
    for p in ("MONTHLY", "QUARTERLY"):
        add_tariff(db, "22A", "PASSENGER", p, "5.000")
    subscription = SubscriptionService.from_session(db).create_subscription(_card(db), "PASSENGER", period, ["22A"], start)
    assert (subscription.valid_from, subscription.valid_until) == (start, expected_end)


def test_add_months_and_end_of_period_helpers():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert end_of_period(date(2026, 1, 1), 12) == date(2026, 12, 31)


def test_subscription_total_is_the_sum_of_its_lines_and_stays_frozen(db, hammam):
    service = SubscriptionService.from_session(db)
    subscription = service.create_subscription(_card(db), "PASSENGER", "ANNUAL", ["22A", "HS"], START)
    assert subscription.total_price == Decimal("61.000")
    add_tariff(db, "22A", "PASSENGER", "ANNUAL", "40.000", valid_from=date(2026, 2, 1))  # le tarif change ensuite
    db.refresh(subscription)
    assert subscription.total_price == Decimal("61.000")  # l'abonnement existant garde son prix


def test_add_a_line_to_an_existing_subscription(db, hammam):
    service = SubscriptionService.from_session(db)
    subscription = service.create_subscription(_card(db), "PASSENGER", "ANNUAL", ["22A"], START)
    service.add_line(subscription, "HS")
    service.add_line(subscription, "HS")  # sans effet : déjà présente
    assert sorted(line.number for line in subscription.lines) == ["22A", "HS"]
    assert subscription.total_price == Decimal("61.000")


def test_unknown_category_period_or_line_are_refused(db):
    service = SubscriptionService.from_session(db)
    with pytest.raises(CategoryNotFoundError):
        service.quote("NOPE", "ANNUAL", ["22A"], START)
    with pytest.raises(PeriodNotFoundError):
        service.quote("PASSENGER", "NOPE", ["22A"], START)
    with pytest.raises(InvalidLineError):
        service.quote("PASSENGER", "ANNUAL", ["999X"], START)


# ---------------------------------------------------------------- extensibilité (sans changer la structure)

def test_new_category_period_and_line_work_without_schema_change(db):
    db.add_all([
        Category(code="RETIRED", name="Retraité", free_travel=False, status="ACTIVE"),
        SubscriptionPeriod(code="BIMONTHLY", name="Bimestriel", months=2, status="ACTIVE"),
        Line(number="77", departure="Sousse", destination="Test", status="ACTIVE"),
    ])
    db.flush()
    add_tariff(db, "77", "RETIRED", "BIMONTHLY", "7.500")
    service = SubscriptionService.from_session(db)
    subscription = service.create_subscription(_card(db), "RETIRED", "BIMONTHLY", ["77"], START)
    assert subscription.total_price == Decimal("7.500")
    assert subscription.valid_until == date(2026, 2, 28)


def test_a_new_free_category_is_just_a_flag(db):
    db.add(Category(code="MARTYRS_FAMILY", name="Famille de martyr", free_travel=True, status="ACTIVE"))
    db.flush()
    assert SubscriptionService.from_session(db).quote("MARTYRS_FAMILY", "ANNUAL", ["22A", "28"], START).total == Decimal("0.000")


# ---------------------------------------------------------------- lien avec le scan

def test_a_subscription_created_by_the_service_covers_the_scan_during_its_validity_only(db):
    from fastapi.testclient import TestClient

    from app.main import app

    card = _card(db, "2000000009")
    add_tariff(db, "22A", "PASSENGER", "MONTHLY", "5.000")
    SubscriptionService.from_session(db).create_subscription(card, "PASSENGER", "MONTHLY", ["22A"], date(2026, 9, 1))
    db.commit()
    http = TestClient(app)
    inside = http.post(PAYMENTS_URL, json=payment_payload(
        card_tag="2000000009", occurred_at="2026-09-30T18:30:00Z")).json()["data"]
    after = http.post(PAYMENTS_URL, json=payment_payload(
        transaction_id="T-2", card_tag="2000000009", occurred_at="2026-10-01T10:00:00Z"))
    assert inside["reason_code"] == "VALID_SUBSCRIPTION"
    assert after.json()["data"]["reason_code"] == "INSUFFICIENT_BALANCE"  # abonnement terminé, solde de la carte = 0
