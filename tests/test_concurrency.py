"""Tests de concurrence : uniquement avec PostgreSQL (SQLite ne supporte pas SELECT ... FOR UPDATE).

    TEST_DATABASE_URL=postgresql+psycopg://scanner:scanner@localhost:5432/test_navio_db pytest tests/test_concurrency.py
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.dependencies.database import SessionLocal, engine
from app.main import app
from app.models import Card
from tests.conftest import CARD_OK, PAYMENTS_URL, balance_of, payment_payload, transaction_count

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="nécessite PostgreSQL")


def _post(payload):
    return TestClient(app).post(PAYMENTS_URL, json=payload)


def test_same_transaction_id_sent_concurrently_is_debited_once():
    payloads = [payment_payload(transaction_id="TRX-RACE", card_tag=CARD_OK)] * 10
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(_post, payloads))
    assert [r.status_code for r in responses].count(200) == 1
    assert all(r.status_code in (200, 409) for r in responses)
    assert balance_of(CARD_OK) == Decimal("8.800")
    assert transaction_count("TRX-RACE") == 1


def test_concurrent_double_scans_of_the_same_trip_are_debited_once():
    """10 scans simultanés, transaction_id différents, même carte / même bus / même ligne."""
    payloads = [payment_payload(transaction_id=f"TRX-{i}", card_tag=CARD_OK) for i in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(_post, payloads))
    reasons = [r.json()["data"]["reason_code"] for r in responses]
    assert reasons.count("BALANCE_DEBITED") == 1
    assert reasons.count("TRIP_ALREADY_VALIDATED") == 9
    assert balance_of(CARD_OK) == Decimal("8.800")


def test_concurrent_payments_never_overdraw_the_card():
    with SessionLocal() as session:
        card = session.query(Card).filter_by(card_tag=CARD_OK).one()
        card.balance = Decimal("3.000")  # 3.000 / 1.200 => exactement 2 paiements possibles
        session.commit()
    # véhicules différents : ce sont bien 10 voyages distincts
    payloads = [
        payment_payload(transaction_id=f"TRX-{i}", card_tag=CARD_OK, vehicle_id=f"BUS-{i}") for i in range(10)
    ]
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(_post, payloads))
    statuses = [r.json()["data"]["status"] for r in responses]
    assert statuses.count("APPROVED") == 2
    assert statuses.count("DECLINED") == 8
    assert balance_of(CARD_OK) == Decimal("0.600")
