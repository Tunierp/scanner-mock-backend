from decimal import Decimal

import pytest

from tests.conftest import PAYMENTS_URL, balance_of, payment_payload, transaction_count


def pay(client, **overrides):
    return client.post(PAYMENTS_URL, json=payment_payload(**overrides))


# 1. carte avec abonnement valide
def test_valid_subscription_is_approved(client):
    response = pay(client)
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "transaction_id": "TRX-000001",
            "status": "APPROVED",
            "payment_method": "SUBSCRIPTION",
            "reason_code": "VALID_SUBSCRIPTION",
            "message": "Voyage couvert par l'abonnement.",
            "amount": 0.0,
            "currency": "TND",
        },
    }


# 12. l'abonnement ne débite pas le solde
def test_subscription_does_not_debit_balance(client):
    pay(client)
    assert balance_of("CARD-TEST-001") == Decimal("10.000")


# 2 + 11. carte sans abonnement, solde suffisant, balance_after correct
def test_balance_payment_debits_and_reports_balances(client):
    response = pay(client, transaction_id="TRX-000002", card_token="CARD-TEST-003")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "APPROVED"
    assert data["payment_method"] == "CARD_BALANCE"
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert data["message"] == "Paiement accepté."
    assert data["amount"] == pytest.approx(0.8)
    assert data["balance_before"] == pytest.approx(10.0)
    assert data["balance_after"] == pytest.approx(9.2)
    assert balance_of("CARD-TEST-003") == Decimal("9.200")


def test_several_payments_accumulate(client):
    pay(client, transaction_id="T-1", card_token="CARD-TEST-003")
    response = pay(client, transaction_id="T-2", card_token="CARD-TEST-003")
    assert response.json()["data"]["balance_before"] == pytest.approx(9.2)
    assert response.json()["data"]["balance_after"] == pytest.approx(8.4)


# 3 + 13. solde insuffisant : refus et solde inchangé
def test_insufficient_balance_is_declined_without_debit(client):
    response = pay(client, transaction_id="TRX-000003", card_token="CARD-TEST-002")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "transaction_id": "TRX-000003",
            "status": "DECLINED",
            "payment_method": None,
            "reason_code": "INSUFFICIENT_BALANCE",
            "message": "Solde insuffisant.",
            "amount": 0.8,
            "currency": "TND",
            "balance": 0.3,
        },
    }
    assert balance_of("CARD-TEST-002") == Decimal("0.300")


# 4. carte inexistante
def test_unknown_card_returns_404(client):
    response = pay(client, card_token="CARD-UNKNOWN")
    assert response.status_code == 404
    assert response.json() == {"success": False, "error": {"code": "CARD_NOT_FOUND", "message": "Carte introuvable."}}
    assert transaction_count() == 0


# 5. carte bloquée
def test_blocked_card_is_declined(client):
    response = pay(client, card_token="CARD-TEST-004")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "DECLINED"
    assert data["reason_code"] == "CARD_BLOCKED"
    assert balance_of("CARD-TEST-004") == Decimal("10.000")


def test_expired_card_is_declined(client):
    data = pay(client, card_token="CARD-TEST-006").json()["data"]
    assert data["status"] == "DECLINED"
    assert data["reason_code"] == "CARD_EXPIRED"
    assert balance_of("CARD-TEST-006") == Decimal("10.000")


# 6. abonnement valide pour une autre route
def test_subscription_for_other_route_falls_back_to_balance(client):
    data = pay(client, transaction_id="T-1", card_token="CARD-TEST-005", route_id="ROUTE-001").json()["data"]
    assert data["payment_method"] == "CARD_BALANCE"
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of("CARD-TEST-005") == Decimal("9.200")


def test_subscription_covers_its_own_route(client):
    data = pay(client, transaction_id="T-2", card_token="CARD-TEST-005", route_id="ROUTE-003").json()["data"]
    assert data["payment_method"] == "SUBSCRIPTION"
    assert data["reason_code"] == "VALID_SUBSCRIPTION"


def test_card_001_on_route_002_is_debited(client):
    data = pay(client, route_id="ROUTE-002").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of("CARD-TEST-001") == Decimal("9.200")


def test_expired_subscription_is_not_used(client):
    data = pay(client, card_token="CARD-TEST-007").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"


def test_subscription_not_valid_before_its_start_date(client):
    data = pay(client, occurred_at="2025-06-01T10:00:00Z").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"


# 7. transaction dupliquée
def test_duplicate_transaction_is_rejected_and_not_debited_twice(client):
    first = pay(client, transaction_id="TRX-DUP", card_token="CARD-TEST-003")
    assert first.status_code == 200
    second = pay(client, transaction_id="TRX-DUP", card_token="CARD-TEST-003")
    assert second.status_code == 409
    body = second.json()
    assert body["success"] is False
    assert body["error"]["code"] == "DUPLICATE_TRANSACTION"
    assert body["error"]["details"]["status"] == "APPROVED"
    assert body["error"]["details"]["balance_after"] == pytest.approx(9.2)
    assert balance_of("CARD-TEST-003") == Decimal("9.200")
    assert transaction_count("TRX-DUP") == 1


def test_same_transaction_id_with_different_data_is_already_processed(client):
    pay(client, transaction_id="TRX-X", card_token="CARD-TEST-003")
    response = pay(client, transaction_id="TRX-X", card_token="CARD-TEST-002")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSACTION_ALREADY_PROCESSED"
    assert balance_of("CARD-TEST-002") == Decimal("0.300")


def test_declined_transaction_is_also_idempotent(client):
    pay(client, transaction_id="TRX-D", card_token="CARD-TEST-002")
    response = pay(client, transaction_id="TRX-D", card_token="CARD-TEST-002")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "DECLINED"


# Validations
def test_invalid_route_returns_400(client):
    response = pay(client, route_id="ROUTE-999")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ROUTE"
    assert balance_of("CARD-TEST-001") == Decimal("10.000")


@pytest.mark.parametrize("fare", [0, -1, 0.8005, 5000])
def test_invalid_fare_returns_400(client, fare):
    response = pay(client, card_token="CARD-TEST-003", fare=fare)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FARE"
    assert balance_of("CARD-TEST-003") == Decimal("10.000")


def test_wrong_currency_returns_400(client):
    response = pay(client, currency="EUR")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FARE"


def test_missing_field_returns_422_with_uniform_format(client):
    payload = payment_payload()
    del payload["card_token"]
    response = client.post(PAYMENTS_URL, json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
