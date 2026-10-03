from decimal import Decimal

import pytest

from tests.conftest import (
    CARD_A, CARD_B, CARD_BLOCKED, CARD_EXPIRED, CARD_LOW, CARD_OK, CARD_OLD_SUB, CARD_SUB, CARD_SUB_R3,
    CARD_UNKNOWN, PAYMENTS_URL, balance_of, payment_payload, transaction_count,
)


def pay(client, **overrides):
    return client.post(PAYMENTS_URL, json=payment_payload(**overrides))


# ---------------------------------------------------------------- abonnement / solde

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
        },
    }


def test_subscription_does_not_debit_balance(client):
    pay(client)
    assert balance_of(CARD_SUB) == Decimal("10.000")


def test_balance_payment_debits_and_reports_balances(client):
    response = pay(client, transaction_id="TRX-000002", card_tag=CARD_OK)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "APPROVED"
    assert data["payment_method"] == "CARD_BALANCE"
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert data["message"] == "Paiement accepté."
    assert data["amount"] == pytest.approx(0.8)
    assert data["balance_before"] == pytest.approx(10.0)
    assert data["balance_after"] == pytest.approx(9.2)
    assert "currency" not in data
    assert balance_of(CARD_OK) == Decimal("9.200")


def test_several_trips_accumulate(client):
    pay(client, transaction_id="T-1", card_tag=CARD_OK, vehicle_id="BUS-001")
    data = pay(client, transaction_id="T-2", card_tag=CARD_OK, vehicle_id="BUS-002").json()["data"]
    assert data["balance_before"] == pytest.approx(9.2)
    assert data["balance_after"] == pytest.approx(8.4)


def test_insufficient_balance_is_declined_without_debit(client):
    response = pay(client, transaction_id="TRX-000003", card_tag=CARD_LOW)
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
            "balance": 0.3,
        },
    }
    assert balance_of(CARD_LOW) == Decimal("0.300")


def test_unknown_card_returns_404(client):
    response = pay(client, card_tag=CARD_UNKNOWN)
    assert response.status_code == 404
    assert response.json() == {"success": False, "error": {"code": "CARD_NOT_FOUND", "message": "Carte introuvable."}}
    assert transaction_count() == 0


def test_blocked_card_is_declined(client):
    response = pay(client, card_tag=CARD_BLOCKED)
    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", "CARD_BLOCKED")
    assert balance_of(CARD_BLOCKED) == Decimal("10.000")


def test_expired_card_is_declined(client):
    data = pay(client, card_tag=CARD_EXPIRED).json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", "CARD_EXPIRED")
    assert balance_of(CARD_EXPIRED) == Decimal("10.000")


def test_subscription_for_other_route_falls_back_to_balance(client):
    data = pay(client, card_tag=CARD_SUB_R3, route_id="ROUTE-001").json()["data"]
    assert (data["payment_method"], data["reason_code"]) == ("CARD_BALANCE", "BALANCE_DEBITED")
    assert balance_of(CARD_SUB_R3) == Decimal("9.200")


def test_subscription_covers_its_own_route(client):
    data = pay(client, card_tag=CARD_SUB_R3, route_id="ROUTE-003").json()["data"]
    assert (data["payment_method"], data["reason_code"]) == ("SUBSCRIPTION", "VALID_SUBSCRIPTION")


def test_subscribed_card_on_other_route_is_debited(client):
    data = pay(client, route_id="ROUTE-002").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_SUB) == Decimal("9.200")


def test_expired_subscription_is_not_used(client):
    assert pay(client, card_tag=CARD_OLD_SUB).json()["data"]["reason_code"] == "BALANCE_DEBITED"


def test_subscription_not_valid_before_its_start_date(client):
    data = pay(client, occurred_at="2025-06-01T10:00:00Z").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"


# ---------------------------------------------------------------- règle du voyage (double scan)

def test_second_scan_same_trip_is_declined_without_second_debit(client):
    first = pay(client, transaction_id="A-1", card_tag=CARD_OK)
    assert first.json()["data"]["reason_code"] == "BALANCE_DEBITED"
    second = pay(client, transaction_id="A-2", card_tag=CARD_OK, occurred_at="2026-09-30T18:32:00Z")
    assert second.status_code == 200
    data = second.json()["data"]
    assert data["status"] == "DECLINED"
    assert data["reason_code"] == "TRIP_ALREADY_VALIDATED"
    assert data["message"] == "Votre voyage est déjà payé/validé."
    assert data["payment_method"] is None
    assert balance_of(CARD_OK) == Decimal("9.200")  # un seul débit


def test_second_scan_after_subscription_validation_is_declined(client):
    assert pay(client, transaction_id="A-1").json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"
    data = pay(client, transaction_id="A-2").json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", "TRIP_ALREADY_VALIDATED")


def test_same_card_in_another_vehicle_is_a_new_trip(client):
    pay(client, transaction_id="A-1", card_tag=CARD_OK, vehicle_id="BUS-001")
    data = pay(client, transaction_id="A-2", card_tag=CARD_OK, vehicle_id="BUS-002").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_OK) == Decimal("8.400")


def test_same_card_on_another_route_in_same_vehicle_is_a_new_trip(client):
    pay(client, transaction_id="A-1", card_tag=CARD_OK, route_id="ROUTE-001")
    data = pay(client, transaction_id="A-2", card_tag=CARD_OK, route_id="ROUTE-002").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"


def test_scan_long_after_the_first_is_a_new_trip(client):
    pay(client, transaction_id="A-1", card_tag=CARD_OK)
    data = pay(client, transaction_id="A-2", card_tag=CARD_OK, occurred_at="2026-09-30T20:45:00Z").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_OK) == Decimal("8.400")


def test_declined_first_scan_does_not_block_a_later_scan(client):
    first = pay(client, transaction_id="A-1", card_tag=CARD_LOW).json()["data"]
    second = pay(client, transaction_id="A-2", card_tag=CARD_LOW).json()["data"]
    assert first["reason_code"] == second["reason_code"] == "INSUFFICIENT_BALANCE"


def test_different_travelers_on_same_bus_are_both_accepted(client):
    first = pay(client, transaction_id="A-1", card_tag=CARD_A).json()["data"]
    second = pay(client, transaction_id="A-2", card_tag=CARD_B).json()["data"]
    assert first["reason_code"] == second["reason_code"] == "BALANCE_DEBITED"


# ---------------------------------------------------------------- identité d'un scan : scanner + transaction_id + heure

def test_two_scanners_can_use_the_same_transaction_id(client):
    """Scénario : « T01 » envoyé par SCANNER-001 (BUS-001) puis par SCANNER-002 (BUS-002)."""
    first = pay(client, transaction_id="T01", card_tag=CARD_A, device_id="SCANNER-001", vehicle_id="BUS-001",
                route_id="ROUTE-001")
    second = pay(client, transaction_id="T01", card_tag=CARD_B, device_id="SCANNER-002", vehicle_id="BUS-002",
                 route_id="ROUTE-002")
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["reason_code"] == "BALANCE_DEBITED"
    assert second.json()["data"]["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_A) == Decimal("9.200") and balance_of(CARD_B) == Decimal("9.200")
    assert transaction_count("T01") == 2


def test_transaction_id_reused_another_day_is_a_new_scan(client):
    """Scénario : BUS-01, transaction_id = 5 aujourd'hui, puis le même id demain (compteur remis à zéro)."""
    today = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:30:00Z")
    tomorrow = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-10-01T18:30:00Z")
    assert today.status_code == 200 and tomorrow.status_code == 200
    assert tomorrow.json()["data"]["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_OK) == Decimal("8.400")  # débité les deux jours
    assert transaction_count("5") == 2


def test_transaction_id_reused_another_day_with_subscription(client):
    pay(client, transaction_id="5", occurred_at="2026-09-30T18:30:00Z")
    data = pay(client, transaction_id="5", occurred_at="2026-10-01T18:30:00Z").json()["data"]
    assert data["reason_code"] == "VALID_SUBSCRIPTION"


def test_retry_with_same_id_and_same_time_is_a_duplicate(client):
    pay(client, transaction_id="5", card_tag=CARD_OK)
    again = pay(client, transaction_id="5", card_tag=CARD_OK)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DUPLICATE_TRANSACTION"
    assert balance_of(CARD_OK) == Decimal("9.200")


def test_retry_with_a_different_time_is_still_never_debited_twice(client):
    """Filet de sécurité : si le scanner renvoie avec une autre heure, la règle du voyage évite le double débit."""
    pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:30:00Z")
    again = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:33:00Z")
    assert again.status_code == 200
    assert again.json()["data"]["reason_code"] == "TRIP_ALREADY_VALIDATED"
    assert balance_of(CARD_OK) == Decimal("9.200")


def test_same_instant_in_another_timezone_is_the_same_scan(client):
    pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:30:00Z")
    again = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T19:30:00+01:00")
    assert again.status_code == 409


def test_duplicate_transaction_is_rejected_and_not_debited_twice(client):
    assert pay(client, transaction_id="TRX-DUP", card_tag=CARD_OK).status_code == 200
    second = pay(client, transaction_id="TRX-DUP", card_tag=CARD_OK)
    assert second.status_code == 409
    body = second.json()
    assert body["success"] is False
    assert body["error"]["code"] == "DUPLICATE_TRANSACTION"
    assert body["error"]["details"]["status"] == "APPROVED"
    assert body["error"]["details"]["balance_after"] == pytest.approx(9.2)
    assert balance_of(CARD_OK) == Decimal("9.200")
    assert transaction_count("TRX-DUP") == 1


def test_same_scanner_same_id_with_different_data_is_already_processed(client):
    pay(client, transaction_id="TRX-X", card_tag=CARD_OK)
    response = pay(client, transaction_id="TRX-X", card_tag=CARD_LOW)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSACTION_ALREADY_PROCESSED"
    assert balance_of(CARD_LOW) == Decimal("0.300")


def test_declined_transaction_is_also_idempotent(client):
    pay(client, transaction_id="TRX-D", card_tag=CARD_LOW)
    response = pay(client, transaction_id="TRX-D", card_tag=CARD_LOW)
    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "DECLINED"


# ---------------------------------------------------------------- validations

def test_invalid_route_returns_400(client):
    response = pay(client, route_id="ROUTE-999")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ROUTE"
    assert balance_of(CARD_SUB) == Decimal("10.000")


@pytest.mark.parametrize("fare", [0, -1, 0.8005, 5000])
def test_invalid_fare_returns_400(client, fare):
    response = pay(client, card_tag=CARD_OK, fare=fare)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FARE"
    assert balance_of(CARD_OK) == Decimal("10.000")


@pytest.mark.parametrize(
    "tag", ["12345", "12345678901", "12345abcde", "1258 46585", "", 1258465854, "١٢٣٤٥٦٧٨٩٠"]
)
def test_card_tag_must_be_exactly_10_digits_as_text(client, tag):
    response = pay(client, card_tag=tag)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_leading_zeros_are_kept(client):
    # « 0000000000 » est un format valide (simplement inconnu ici)
    assert pay(client, card_tag="0000000000").status_code == 404


def test_missing_field_returns_422_with_uniform_format(client):
    payload = payment_payload()
    del payload["card_tag"]
    response = client.post(PAYMENTS_URL, json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
