"""Tests de concurrence : uniquement avec PostgreSQL (SQLite ne supporte pas SELECT ... FOR UPDATE).

    TEST_DATABASE_URL=postgresql+psycopg://scanner:scanner@localhost:5433/scanner_mock pytest tests/test_concurrency.py
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.dependencies.database import SessionLocal, engine
from app.main import app
from app.models import Card
from tests.conftest import PAYMENTS_URL, balance_of, payment_payload, transaction_count

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="nécessite PostgreSQL")


def _post(payload):
    return TestClient(app).post(PAYMENTS_URL, json=payload)


def test_same_transaction_id_sent_concurrently_is_debited_once():
    payloads = [payment_payload(transaction_id="TRX-RACE", card_token="CARD-TEST-003")] * 10
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(_post, payloads))
    assert sorted(r.status_code for r in responses).count(200) == 1
    assert all(r.status_code in (200, 409) for r in responses)
    assert balance_of("CARD-TEST-003") == Decimal("9.200")
    assert transaction_count("TRX-RACE") == 1


def test_concurrent_payments_never_overdraw_the_card():
    with SessionLocal() as session:
        card = session.query(Card).filter_by(card_token="CARD-TEST-003").one()
        card.balance = Decimal("2.000")  # 2.000 / 0.800 => exactement 2 paiements possibles
        session.commit()
    payloads = [payment_payload(transaction_id=f"TRX-{i}", card_token="CARD-TEST-003") for i in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(_post, payloads))
    statuses = [r.json()["data"]["status"] for r in responses]
    assert statuses.count("APPROVED") == 2
    assert statuses.count("DECLINED") == 8
    assert balance_of("CARD-TEST-003") == Decimal("0.400")
