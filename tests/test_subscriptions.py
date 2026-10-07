"""Abonnements : liaisons (corridors), tarifs configurables, prix, une période par abonnement, validité."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    CategoryNotFoundError, CorridorNotFoundError, PeriodNotFoundError, SubscriptionFareNotFoundError,
)
from app.dependencies.database import SessionLocal
from app.main import app
from app.models import Category, Corridor, Line, SubscriptionFare, SubscriptionPeriod
from app.services.card_service import CardService
from app.services.subscription_service import SubscriptionService, add_months, end_of_period
from app.services.user_service import UserService
from tests.conftest import PAYMENTS_URL, payment_payload

START = date(2026, 1, 1)
MSAKEN, HAMMAM, MONASTIR = "SOUSSE-MSAKEN", "SOUSSE-HAMMAM-SOUSSE", "SOUSSE-MONASTIR"


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _id(db, model, **where):
    return db.scalar(select(model.id).filter_by(**where))


def add_fare(db, corridor, category, period, amount, valid_from=date(2025, 1, 1)):
    db.add(SubscriptionFare(
        category_id=_id(db, Category, type="SUBSCRIPTION", code=category), corridor_id=_id(db, Corridor, code=corridor),
        period_id=_id(db, SubscriptionPeriod, code=period), amount=Decimal(amount), valid_from=valid_from,
    ))
    db.flush()


def new_card(db, tag="2000000001", balance="0.000"):
    user = UserService.from_session(db).create_user("Sana", f"Ben Ali {tag}")
    return CardService.from_session(db).issue_card(user, tag, balance=Decimal(balance))


def scan(line, card_tag, transaction_id="T-1"):
    return TestClient(app).post(PAYMENTS_URL, json=payment_payload(
        transaction_id=transaction_id, card_tag=card_tag, line_number=line)).json()["data"]["reason_code"]


# ---------------------------------------------------------------- prix des abonnements

def test_annual_price_is_the_sum_of_the_corridor_fares(db):
    quote = SubscriptionService.from_session(db).quote("PASSENGER", "ANNUAL", [MSAKEN, HAMMAM], START)
    assert [(q.corridor.code, q.amount) for q in quote.corridors] == [(MSAKEN, Decimal("31.000")), (HAMMAM, Decimal("30.000"))]
    assert quote.total == Decimal("61.000")  # 31.000 + 30.000


def test_semiannual_price_uses_the_semiannual_fares(db):
    assert SubscriptionService.from_session(db).quote("PASSENGER", "SEMIANNUAL", [MSAKEN, HAMMAM], START).total == Decimal("31.000")


def test_two_bus_lines_on_one_corridor_are_not_charged_twice(db):
    """Sousse - Msaken est desservie par 22A ET 22B : 31 DT, pas 62."""
    service = SubscriptionService.from_session(db)
    assert service.quote("PASSENGER", "ANNUAL", [MSAKEN], START).total == Decimal("31.000")
    assert service.quote("PASSENGER", "ANNUAL", [MSAKEN, MSAKEN], START).total == Decimal("31.000")  # doublon ignoré
    sub = service.create_subscription(new_card(db), "PASSENGER", "ANNUAL", [MSAKEN], START)
    assert sub.amount == Decimal("31.000")
    assert sorted(line.number for corridor in sub.corridors for line in corridor.lines) == ["22A", "22B"]


def test_the_fare_depends_on_the_category(db):
    add_fare(db, MSAKEN, "UNIVERSITY", "ANNUAL", "20.000")
    add_fare(db, HAMMAM, "UNIVERSITY", "ANNUAL", "18.000")
    service = SubscriptionService.from_session(db)
    assert service.quote("PASSENGER", "ANNUAL", [MSAKEN, HAMMAM], START).total == Decimal("61.000")
    assert service.quote("UNIVERSITY", "ANNUAL", [MSAKEN, HAMMAM], START).total == Decimal("38.000")


def test_the_fare_is_historized_by_start_date(db):
    add_fare(db, MSAKEN, "PASSENGER", "ANNUAL", "33.000", valid_from=date(2026, 6, 1))
    service = SubscriptionService.from_session(db)
    assert service.quote("PASSENGER", "ANNUAL", [MSAKEN], date(2026, 5, 31)).total == Decimal("31.000")
    assert service.quote("PASSENGER", "ANNUAL", [MSAKEN], date(2026, 6, 1)).total == Decimal("33.000")


def test_the_price_paid_stays_frozen_when_fares_change(db):
    sub = SubscriptionService.from_session(db).create_subscription(new_card(db), "PASSENGER", "ANNUAL", [MSAKEN, HAMMAM], START)
    add_fare(db, MSAKEN, "PASSENGER", "ANNUAL", "40.000", valid_from=date(2026, 2, 1))
    db.refresh(sub)
    assert sub.amount == Decimal("61.000")


# ---------------------------------------------------------------- un abonnement = une seule période

def test_a_semiannual_subscription_only_accepts_corridors_with_a_semiannual_fare(db):
    """Sousse - Monastir n'a qu'un tarif annuel : refusée dans un abonnement semestriel (jamais de mélange)."""
    with pytest.raises(SubscriptionFareNotFoundError):
        SubscriptionService.from_session(db).quote("PASSENGER", "SEMIANNUAL", [MSAKEN, MONASTIR], START)


def test_adding_a_corridor_without_a_fare_for_the_subscription_period_is_refused(db):
    service = SubscriptionService.from_session(db)
    sub = service.create_subscription(new_card(db), "PASSENGER", "SEMIANNUAL", [MSAKEN], START)
    with pytest.raises(SubscriptionFareNotFoundError):
        service.add_corridor(sub, MONASTIR)  # pas de tarif semestriel
    service.add_corridor(sub, HAMMAM)  # a un tarif semestriel
    assert sub.amount == Decimal("31.000")


def test_annual_and_semiannual_corridors_need_two_subscriptions_on_the_same_card(db):
    card = new_card(db, "2000000005")
    service = SubscriptionService.from_session(db)
    annual = service.create_subscription(card, "PASSENGER", "ANNUAL", [MONASTIR], START)
    semiannual = service.create_subscription(card, "PASSENGER", "SEMIANNUAL", [MSAKEN], START)
    db.commit()
    assert (annual.period.code, semiannual.period.code) == ("ANNUAL", "SEMIANNUAL")
    assert (annual.valid_until, semiannual.valid_until) == (date(2026, 12, 31), date(2026, 6, 30))
    assert scan("52A", "2000000005", "A") == "VALID_SUBSCRIPTION"  # liaison annuelle
    assert scan("22A", "2000000005", "B") == "VALID_SUBSCRIPTION"  # liaison semestrielle


def test_each_link_keeps_the_period_and_the_fare_of_its_subscription(db):
    sub = SubscriptionService.from_session(db).create_subscription(new_card(db), "PASSENGER", "ANNUAL", [MSAKEN, HAMMAM], START)
    db.flush()
    annual_id = _id(db, SubscriptionPeriod, code="ANNUAL")
    assert {sc.period_id for sc in sub.subscription_corridors} == {annual_id}
    fares = {f.id: f for f in db.scalars(select(SubscriptionFare))}
    assert all(fares[sc.fare_id].period_id == annual_id and fares[sc.fare_id].corridor_id == sc.corridor_id
               for sc in sub.subscription_corridors)


# ---------------------------------------------------------------- couverture au scan : tous les bus d'une liaison

def test_hammam_sousse_subscription_covers_buses_of_wider_routes(db):
    """Un bus Sousse - Kalaa Kebira (15*) ou Sousse - Sidi Bou Ali (17) qui passe par Hammam Sousse est couvert."""
    SubscriptionService.from_session(db).create_subscription(new_card(db), "PASSENGER", "ANNUAL", [HAMMAM], START)
    db.commit()
    assert scan("15", "2000000001", "A") == "VALID_SUBSCRIPTION"
    assert scan("17", "2000000001", "B") == "VALID_SUBSCRIPTION"
    assert scan("22A", "2000000001", "C") == "INSUFFICIENT_BALANCE"  # 22A n'appartient pas à cette liaison (solde 0)


def test_msaken_subscription_covers_22a_and_22b(db):
    SubscriptionService.from_session(db).create_subscription(new_card(db), "PASSENGER", "ANNUAL", [MSAKEN], START)
    db.commit()
    assert scan("22A", "2000000001", "A") == "VALID_SUBSCRIPTION"
    assert scan("22B", "2000000001", "B") == "VALID_SUBSCRIPTION"


# ---------------------------------------------------------------- catégorie à gratuité totale

def test_disabled_category_is_free_whatever_the_fares(db):
    quote = SubscriptionService.from_session(db).quote("DISABLED", "ANNUAL", [MSAKEN, MONASTIR, HAMMAM], START)
    assert quote.total == Decimal("0.000") and all(q.fare_id is None for q in quote.corridors)


def test_disabled_subscription_may_have_no_corridor_but_others_need_one(db):
    card = new_card(db)
    service = SubscriptionService.from_session(db)
    assert service.create_subscription(card, "DISABLED", "ANNUAL", [], START).amount == Decimal("0.000")
    with pytest.raises(CorridorNotFoundError):
        service.create_subscription(card, "PASSENGER", "ANNUAL", [], START)


# ---------------------------------------------------------------- durée

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
def test_validity_comes_from_the_subscription_period(db, period, start, expected_end):
    for p in ("MONTHLY", "QUARTERLY"):
        add_fare(db, MSAKEN, "PASSENGER", p, "5.000")
    sub = SubscriptionService.from_session(db).create_subscription(new_card(db), "PASSENGER", period, [MSAKEN], start)
    assert (sub.valid_from, sub.valid_until) == (start, expected_end)


def test_add_months_and_end_of_period_helpers():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert end_of_period(date(2026, 1, 1), 12) == date(2026, 12, 31)


def test_a_subscription_covers_the_scan_during_its_validity_only(db):
    add_fare(db, MSAKEN, "PASSENGER", "MONTHLY", "5.000")
    SubscriptionService.from_session(db).create_subscription(new_card(db), "PASSENGER", "MONTHLY", [MSAKEN], date(2026, 9, 1))
    db.commit()
    http = TestClient(app)
    inside = http.post(PAYMENTS_URL, json=payment_payload(card_tag="2000000001", occurred_at="2026-09-30T18:30:00Z"))
    after = http.post(PAYMENTS_URL, json=payment_payload(
        transaction_id="T-2", card_tag="2000000001", occurred_at="2026-10-01T10:00:00Z"))
    assert inside.json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"
    assert after.json()["data"]["reason_code"] == "INSUFFICIENT_BALANCE"  # terminé ; solde de la carte = 0


# ---------------------------------------------------------------- erreurs

def test_unknown_category_period_or_corridor_are_refused(db):
    service = SubscriptionService.from_session(db)
    with pytest.raises(CategoryNotFoundError):
        service.quote("NOPE", "ANNUAL", [MSAKEN], START)
    with pytest.raises(PeriodNotFoundError):
        service.quote("PASSENGER", "NOPE", [MSAKEN], START)
    with pytest.raises(CorridorNotFoundError):
        service.quote("PASSENGER", "ANNUAL", ["NOPE"], START)


def test_missing_fare_is_an_error_not_a_zero_price(db):
    with pytest.raises(SubscriptionFareNotFoundError):
        SubscriptionService.from_session(db).quote("PASSENGER", "MONTHLY", [MSAKEN], START)


def test_add_a_corridor_to_an_existing_subscription(db):
    service = SubscriptionService.from_session(db)
    sub = service.create_subscription(new_card(db), "PASSENGER", "ANNUAL", [MSAKEN], START)
    service.add_corridor(sub, HAMMAM)
    service.add_corridor(sub, HAMMAM)  # sans effet : déjà présente
    assert sorted(c.code for c in sub.corridors) == [HAMMAM, MSAKEN]
    assert sub.amount == Decimal("61.000")


# ---------------------------------------------------------------- catégories : une seule table, colonne `type`

def test_category_codes_are_unique_per_type_not_globally(db):
    db.add(Category(type="USER", code="PASSENGER", name="Passager (catégorie d'utilisateur)", status="ACTIVE"))
    db.flush()  # même code, autre type : autorisé
    db.add(Category(type="SUBSCRIPTION", code="PASSENGER", name="doublon", status="ACTIVE"))
    with pytest.raises(IntegrityError):
        db.flush()  # même (type, code) : refusé
    db.rollback()


def test_a_subscription_cannot_use_a_category_of_another_type(db):
    db.add_all([
        Category(type="BUS", code="MINIBUS", name="Minibus", status="ACTIVE"),
        Category(type="USER", code="VIP", name="VIP", status="ACTIVE"),
    ])
    db.flush()
    service = SubscriptionService.from_session(db)
    for code in ("MINIBUS", "VIP"):
        with pytest.raises(CategoryNotFoundError):
            service.quote(code, "ANNUAL", [MSAKEN], START)


def test_new_category_period_corridor_and_fare_need_no_schema_change(db):
    db.add_all([
        Category(type="SUBSCRIPTION", code="RETIRED", name="Retraité", free_travel=False, status="ACTIVE"),
        SubscriptionPeriod(code="BIMONTHLY", name="Bimestriel", months=2, status="ACTIVE"),
        Corridor(code="SOUSSE-TEST", name="Sousse - Test", departure="Sousse", destination="Test", status="ACTIVE"),
    ])
    db.flush()
    add_fare(db, "SOUSSE-TEST", "RETIRED", "BIMONTHLY", "7.500")
    sub = SubscriptionService.from_session(db).create_subscription(new_card(db), "RETIRED", "BIMONTHLY", ["SOUSSE-TEST"], START)
    assert sub.amount == Decimal("7.500") and sub.valid_until == date(2026, 2, 28)


def test_a_new_free_category_is_just_a_flag(db):
    db.add(Category(type="SUBSCRIPTION", code="MARTYRS_FAMILY", name="Famille de martyr", free_travel=True, status="ACTIVE"))
    db.flush()
    assert SubscriptionService.from_session(db).quote("MARTYRS_FAMILY", "ANNUAL", [MSAKEN, HAMMAM], START).total == Decimal("0.000")


def test_a_line_can_be_added_to_a_corridor_without_schema_change(db):
    from app.models import CorridorLine

    db.add(Line(number="99Z", departure="Sousse", destination="Msaken", status="ACTIVE"))
    db.flush()
    db.add(CorridorLine(corridor_id=_id(db, Corridor, code=MSAKEN), line_id=_id(db, Line, number="99Z")))
    SubscriptionService.from_session(db).create_subscription(new_card(db), "PASSENGER", "ANNUAL", [MSAKEN], START)
    db.commit()
    assert scan("99Z", "2000000001", "A") == "VALID_SUBSCRIPTION"
