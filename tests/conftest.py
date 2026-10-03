"""Fixtures de test.

Par défaut les tests utilisent SQLite en mémoire (rapide, sans dépendance).
Pour tester contre PostgreSQL (verrous SELECT ... FOR UPDATE réels + test de concurrence) :

    TEST_DATABASE_URL=postgresql+psycopg://scanner:scanner@localhost:5433/scanner_mock pytest

⚠ La base ciblée est vidée (drop_all) avant chaque test : utilisez une base dédiée aux tests.
"""
import os
from decimal import Decimal

# Doit être positionné AVANT l'import de l'application.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.dependencies.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Card, Transaction  # noqa: E402
from app.seed import seed  # noqa: E402

# Cartes de test (voir app/seed.py)
CARD_SUB = "1000000001"      # 10.000 TND, abonnement ROUTE-001
CARD_LOW = "1000000002"      # 0.300 TND
CARD_OK = "1000000003"       # 10.000 TND, sans abonnement
CARD_BLOCKED = "1000000004"  # bloquée
CARD_SUB_R3 = "1000000005"   # 10.000 TND, abonnement ROUTE-003
CARD_EXPIRED = "1000000006"  # expirée
CARD_OLD_SUB = "1000000007"  # abonnement périmé
CARD_A = "1258465854"        # 10.000 TND, sans abonnement
CARD_B = "1258465855"        # 10.000 TND, sans abonnement
CARD_UNKNOWN = "9999999999"

PAYMENTS_URL = "/api/v1/scanner/payments"
SYNC_URL = "/api/v1/scanner/sync/transactions"


@pytest.fixture(autouse=True)
def _fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def payment_payload(**overrides) -> dict:
    payload = {
        "transaction_id": "TRX-000001",
        "card_tag": CARD_SUB,
        "device_id": "SCANNER-001",
        "vehicle_id": "BUS-001",
        "route_id": "ROUTE-001",
        "fare": 0.8,
        "occurred_at": "2026-09-30T18:30:00Z",
    }
    payload.update(overrides)
    return payload


def sync_item(**overrides) -> dict:
    item = payment_payload(**overrides)
    item.pop("device_id", None)
    return item


def balance_of(card_tag: str) -> Decimal:
    with SessionLocal() as session:
        return Decimal(session.scalar(select(Card.balance).where(Card.card_tag == card_tag)))


def transaction_count(transaction_id: str | None = None) -> int:
    with SessionLocal() as session:
        stmt = select(func.count(Transaction.id))
        if transaction_id:
            stmt = stmt.where(Transaction.transaction_id == transaction_id)
        return session.scalar(stmt)
