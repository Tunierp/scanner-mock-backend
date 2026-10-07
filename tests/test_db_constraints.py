"""Garanties de la BASE (clés étrangères composites) : uniquement PostgreSQL.

SQLite n'applique pas les clés étrangères par défaut. Lancer avec :
    TEST_DATABASE_URL=postgresql+psycopg://scanner:scanner@localhost:5432/test_navio_db pytest tests/test_db_constraints.py
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies.database import SessionLocal, engine
from app.models import Category, Corridor, Subscription, SubscriptionCorridor, SubscriptionFare, SubscriptionPeriod
from app.services.card_service import CardService
from app.services.subscription_service import SubscriptionService
from app.services.user_service import UserService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="nécessite PostgreSQL")


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _annual_subscription(db):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    card = CardService.from_session(db).issue_card(user, "2000000001")
    return SubscriptionService.from_session(db).create_subscription(
        card, "PASSENGER", "ANNUAL", ["SOUSSE-MSAKEN"], date(2026, 1, 1))


def _id(db, model, **where):
    return db.scalar(select(model.id).filter_by(**where))


def test_a_subscription_cannot_point_to_a_category_of_another_type(db):
    bus = Category(type="BUS", code="MINIBUS", name="Minibus", status="ACTIVE")
    db.add(bus)
    db.flush()
    sub = _annual_subscription(db)
    sub.category_id = bus.id  # (bus.id, 'SUBSCRIPTION') n'existe pas dans categories
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_link_cannot_have_a_period_different_from_its_subscription(db):
    sub = _annual_subscription(db)
    db.flush()
    db.add(SubscriptionCorridor(
        subscription_id=sub.id, corridor_id=_id(db, Corridor, code="SOUSSE-HAMMAM-SOUSSE"),
        period_id=_id(db, SubscriptionPeriod, code="SEMIANNUAL"), fare_id=None))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_link_cannot_use_a_fare_of_another_period(db):
    """Abonnement annuel + tarif SEMESTRIEL de la liaison Hammam Sousse : refusé par la base."""
    sub = _annual_subscription(db)
    db.flush()
    hammam = _id(db, Corridor, code="SOUSSE-HAMMAM-SOUSSE")
    semiannual_fare = db.scalar(select(SubscriptionFare.id).where(
        SubscriptionFare.corridor_id == hammam,
        SubscriptionFare.period_id == _id(db, SubscriptionPeriod, code="SEMIANNUAL")))
    db.add(SubscriptionCorridor(
        subscription_id=sub.id, corridor_id=hammam, period_id=sub.period_id, fare_id=semiannual_fare))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_link_cannot_use_the_fare_of_another_corridor(db):
    sub = _annual_subscription(db)
    db.flush()
    hammam = _id(db, Corridor, code="SOUSSE-HAMMAM-SOUSSE")
    msaken_fare = db.scalar(select(SubscriptionFare.id).where(
        SubscriptionFare.corridor_id == _id(db, Corridor, code="SOUSSE-MSAKEN"),
        SubscriptionFare.period_id == sub.period_id))
    db.add(SubscriptionCorridor(
        subscription_id=sub.id, corridor_id=hammam, period_id=sub.period_id, fare_id=msaken_fare))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
