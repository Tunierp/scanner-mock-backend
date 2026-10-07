"""API TEMPORAIRE de réinitialisation des données de test (à supprimer avec l'API)."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.dependencies.database import SessionLocal
from app.main import app, create_app
from app.models import Card, Line
from tests.conftest import (
    CARD_A, CARD_B, CARD_BLOCKED, CARD_LOW, CARD_OK, PAYMENTS_URL, balance_of, payment_payload, transaction_count,
)

RESET_URL = "/api/v1/test-data/reset"


def pay(client, **overrides):
    return client.post(PAYMENTS_URL, json=payment_payload(**overrides))


def test_reset_deletes_all_transactions_and_restores_balances(client):
    pay(client, transaction_id="T-1", card_tag=CARD_OK)  # débit
    pay(client, transaction_id="T-2", card_tag=CARD_LOW)  # refus enregistré
    pay(client, transaction_id="T-3", card_tag=CARD_A)
    assert transaction_count() == 3 and balance_of(CARD_OK) == Decimal("8.800")

    response = client.post(RESET_URL)
    assert response.status_code == 200
    data = response.json()["data"]
    assert response.json()["success"] is True and data["deleted_transactions"] == 3
    assert transaction_count() == 0
    assert balance_of(CARD_OK) == Decimal("10.000") and balance_of(CARD_A) == Decimal("10.000")


def test_reset_needs_no_body_and_returns_the_state_of_the_test_cards(client):
    cards = {c["card_tag"]: c for c in client.post(RESET_URL).json()["data"]["cards"]}
    assert len(cards) == 15
    assert cards["1000000002"] == {"card_tag": "1000000002", "status": "ACTIVE", "balance": 0.3}
    assert cards["1000000004"]["status"] == "BLOCKED" and cards["1000000006"]["status"] == "EXPIRED"
    assert cards["1000000009"]["status"] == "LOST" and cards["1236547895"]["balance"] == 10.0


def test_transaction_ids_can_be_reused_after_a_reset(client):
    assert pay(client, transaction_id="TRX-1", card_tag=CARD_OK).status_code == 200
    assert pay(client, transaction_id="TRX-1", card_tag=CARD_OK).status_code == 409  # doublon
    client.post(RESET_URL)
    again = pay(client, transaction_id="TRX-1", card_tag=CARD_OK)
    assert again.status_code == 200 and again.json()["data"]["reason_code"] == "BALANCE_DEBITED"


def test_reset_restores_card_status_and_balance_changed_by_hand(client):
    with SessionLocal() as db:
        blocked = db.scalar(select(Card).where(Card.card_tag == CARD_BLOCKED))
        blocked.status, blocked.balance = "ACTIVE", Decimal("0.000")
        db.commit()
    client.post(RESET_URL)
    with SessionLocal() as db:
        card = db.scalar(select(Card).where(Card.card_tag == CARD_BLOCKED))
        assert (card.status, Decimal(card.balance)) == ("BLOCKED", Decimal("10.000"))


def test_reset_recreates_missing_test_cards(client):
    with SessionLocal() as db:
        db.delete(db.scalar(select(Card).where(Card.card_tag == CARD_B)))
        db.commit()
    client.post(RESET_URL)
    assert balance_of(CARD_B) == Decimal("10.000")


def test_reset_keeps_data_added_outside_the_seed(client):
    with SessionLocal() as db:
        db.add(Line(number="99Z", departure="Sousse", destination="Test", status="ACTIVE"))
        db.commit()
    client.post(RESET_URL)
    with SessionLocal() as db:
        assert db.scalar(select(Line.id).where(Line.number == "99Z")) is not None


def test_reset_can_be_called_twice(client):
    pay(client, card_tag=CARD_OK)
    assert client.post(RESET_URL).json()["data"]["deleted_transactions"] == 1
    assert client.post(RESET_URL).json()["data"]["deleted_transactions"] == 0


# ---------------------------------------------------------------- jeton optionnel

@pytest.fixture
def with_token():
    app.dependency_overrides[get_settings] = lambda: Settings(test_data_reset_token="s3cret")
    yield
    app.dependency_overrides.pop(get_settings, None)


def test_token_is_required_when_the_server_defines_one(client, with_token):
    pay(client, card_tag=CARD_OK)
    for headers in ({}, {"X-Reset-Token": "wrong"}):
        response = client.post(RESET_URL, headers=headers)
        assert (response.status_code, response.json()["error"]["code"]) == (403, "RESET_FORBIDDEN")
    assert transaction_count() == 1  # rien n'a été supprimé
    assert client.post(RESET_URL, headers={"X-Reset-Token": "s3cret"}).status_code == 200
    assert transaction_count() == 0


# ---------------------------------------------------------------- interrupteur

def test_endpoint_is_absent_when_disabled():
    disabled = TestClient(create_app(Settings(test_data_reset_enabled=False)))
    response = disabled.post(RESET_URL)
    assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert RESET_URL not in disabled.get("/openapi.json").json()["paths"]


def test_endpoint_is_documented_in_swagger_as_temporary(client):
    operation = client.get("/openapi.json").json()["paths"][RESET_URL]["post"]
    assert "TEMPORAIRE" in operation["tags"][0] and "temporaire" in operation["summary"]
