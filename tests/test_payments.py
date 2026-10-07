from decimal import Decimal

import pytest

from tests.conftest import (
    CARD_A, CARD_AHMAD, CARD_BLOCKED, CARD_B, CARD_EXPIRED, CARD_FREE, CARD_INACTIVE, CARD_LOST, CARD_LOW, CARD_OK,
    CARD_OLD_SUB, CARD_REPLACED, CARD_RIM_ACTIVE, CARD_SUB, CARD_SUB_L, CARD_UNKNOWN,
    L22A, L28, L52A, L61, PAYMENTS_URL, balance_of, payment_payload, transaction_count,
)


def pay(client, **overrides):
    return client.post(PAYMENTS_URL, json=payment_payload(**overrides))


# ---------------------------------------------------------------- abonnement (plusieurs lignes)

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


@pytest.mark.parametrize("line", [L22A, "22B", L52A, "52B", "52C", L61])
def test_subscription_covers_every_bus_line_of_its_corridors(client, line):
    """L'abonnement de la carte 1000000001 = liaisons Sousse-Msaken (22A, 22B), Sousse-Monastir (52A, 52B, 52C), Sousse-Jammel (61).
    Les lignes sans tarif au trajet (22B, 52x, 61) sont couvertes quand même : l'abonnement n'en a pas besoin."""
    data = pay(client, line_number=line).json()["data"]
    assert (data["status"], data["reason_code"]) == ("APPROVED", "VALID_SUBSCRIPTION")
    assert balance_of(CARD_SUB) == Decimal("10.000")


def test_a_line_can_belong_to_several_subscriptions(client):
    """La ligne 61 est dans l'abonnement de la carte 1000000001 ET dans celui de la carte 1000000005."""
    assert pay(client, transaction_id="A", card_tag=CARD_SUB, line_number=L61).json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"
    assert pay(client, transaction_id="B", card_tag=CARD_SUB_L, line_number=L61).json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"


def test_subscription_does_not_cover_a_line_it_does_not_contain(client):
    # 28 n'est dans aucun abonnement et n'a pas de tarif
    response = pay(client, line_number=L28)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FARE_NOT_FOUND"


def test_subscription_for_other_line_falls_back_to_balance(client):
    data = pay(client, card_tag=CARD_SUB_L, line_number=L22A).json()["data"]  # SUB-002 ne couvre que la 61
    assert (data["payment_method"], data["reason_code"]) == ("CARD_BALANCE", "BALANCE_DEBITED")
    assert balance_of(CARD_SUB_L) == Decimal("8.800")


def test_expired_subscription_is_not_used(client):
    assert pay(client, card_tag=CARD_OLD_SUB).json()["data"]["reason_code"] == "BALANCE_DEBITED"


def test_subscription_not_valid_before_its_start_date(client):
    data = pay(client, occurred_at="2025-06-01T10:00:00Z").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert data["amount"] == pytest.approx(1.2)


# ---------------------------------------------------------------- solde et tarifs

def test_balance_payment_uses_the_line_fare_and_reports_balances(client):
    response = pay(client, transaction_id="TRX-000002", card_tag=CARD_OK)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "APPROVED"
    assert data["payment_method"] == "CARD_BALANCE"
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert data["message"] == "Paiement accepté."
    assert data["amount"] == pytest.approx(1.2)  # tarif courant de la 22A (un sens)
    assert data["balance_before"] == pytest.approx(10.0)
    assert data["balance_after"] == pytest.approx(8.8)
    assert balance_of(CARD_OK) == Decimal("8.800")


def test_several_trips_accumulate(client):
    pay(client, transaction_id="T-1", card_tag=CARD_OK, vehicle_id="BUS-001")
    data = pay(client, transaction_id="T-2", card_tag=CARD_OK, vehicle_id="BUS-002").json()["data"]
    assert data["balance_before"] == pytest.approx(8.8)
    assert data["balance_after"] == pytest.approx(7.6)


@pytest.mark.parametrize(
    "occurred_at, expected",
    [
        ("2023-05-11T23:30:00Z", 1.1),  # 2023-05-12 00:30 à Tunis -> premier jour du 1er tarif
        ("2023-05-12T10:00:00Z", 1.1),
        ("2024-06-01T10:00:00Z", 1.1),
        ("2024-12-31T12:00:00Z", 1.1),
        ("2024-12-31T23:30:00Z", 1.2),  # 2025-01-01 00:30 à Tunis -> nouveau tarif
        ("2025-01-01T12:00:00Z", 1.2),
        ("2026-09-30T18:30:00Z", 1.2),
    ],
)
def test_fare_depends_on_the_scan_date(client, occurred_at, expected):
    data = pay(client, card_tag=CARD_OK, occurred_at=occurred_at).json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert data["amount"] == pytest.approx(expected)
    assert balance_of(CARD_OK) == Decimal("10.000") - Decimal(str(expected))


def test_no_fare_before_the_first_fare_date(client):
    response = pay(client, card_tag=CARD_OK, occurred_at="2023-05-11T22:30:00Z")  # 23:30 à Tunis, le 11/05
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FARE_NOT_FOUND"


def test_line_without_fare_returns_404_and_nothing_is_recorded(client):
    response = pay(client, card_tag=CARD_OK, line_number=L28)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FARE_NOT_FOUND"
    assert balance_of(CARD_OK) == Decimal("10.000")
    assert transaction_count() == 0


def test_fare_sent_by_the_scanner_is_ignored(client):
    data = pay(client, card_tag=CARD_OK, fare=99, currency="EUR").json()["data"]
    assert data["amount"] == pytest.approx(1.2)


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
            "amount": 1.2,
            "balance": 0.3,
        },
    }
    assert balance_of(CARD_LOW) == Decimal("0.300")


# ---------------------------------------------------------------- cartes

def test_unknown_card_returns_404(client):
    response = pay(client, card_tag=CARD_UNKNOWN)
    assert response.status_code == 404
    assert response.json() == {"success": False, "error": {"code": "CARD_NOT_FOUND", "message": "Carte introuvable."}}
    assert transaction_count() == 0


def test_blocked_card_is_declined(client):
    data = pay(client, card_tag=CARD_BLOCKED).json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", "CARD_BLOCKED")
    assert balance_of(CARD_BLOCKED) == Decimal("10.000")


def test_expired_card_is_declined(client):
    data = pay(client, card_tag=CARD_EXPIRED).json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", "CARD_EXPIRED")
    assert balance_of(CARD_EXPIRED) == Decimal("10.000")


# ---------------------------------------------------------------- règle du voyage (double scan)

def test_second_scan_same_trip_is_declined_without_second_debit(client):
    assert pay(client, transaction_id="A-1", card_tag=CARD_OK).json()["data"]["reason_code"] == "BALANCE_DEBITED"
    second = pay(client, transaction_id="A-2", card_tag=CARD_OK, occurred_at="2026-09-30T18:32:00Z")
    assert second.status_code == 200
    data = second.json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", "TRIP_ALREADY_VALIDATED")
    assert data["message"] == "Votre voyage est déjà payé/validé."
    assert data["payment_method"] is None
    assert balance_of(CARD_OK) == Decimal("8.800")  # un seul débit


def test_second_scan_after_subscription_validation_is_declined(client):
    assert pay(client, transaction_id="A-1").json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"
    data = pay(client, transaction_id="A-2").json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", "TRIP_ALREADY_VALIDATED")


def test_same_card_in_another_vehicle_is_a_new_trip(client):
    pay(client, transaction_id="A-1", card_tag=CARD_OK, vehicle_id="BUS-001")
    data = pay(client, transaction_id="A-2", card_tag=CARD_OK, vehicle_id="BUS-002").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_OK) == Decimal("7.600")


def test_same_card_on_another_line_in_same_vehicle_is_a_new_trip(client):
    assert pay(client, transaction_id="A-1", line_number=L22A).json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"
    assert pay(client, transaction_id="A-2", line_number=L52A).json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"


def test_scan_long_after_the_first_is_a_new_trip(client):
    pay(client, transaction_id="A-1", card_tag=CARD_OK)
    data = pay(client, transaction_id="A-2", card_tag=CARD_OK, occurred_at="2026-09-30T20:45:00Z").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_OK) == Decimal("7.600")


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
    first = pay(client, transaction_id="T01", card_tag=CARD_A, device_id="SCANNER-001", vehicle_id="BUS-001")
    second = pay(client, transaction_id="T01", card_tag=CARD_B, device_id="SCANNER-002", vehicle_id="BUS-002")
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["reason_code"] == second.json()["data"]["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_A) == Decimal("8.800") and balance_of(CARD_B) == Decimal("8.800")
    assert transaction_count("T01") == 2


def test_transaction_id_reused_another_day_is_a_new_scan(client):
    today = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:30:00Z")
    tomorrow = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-10-01T18:30:00Z")
    assert today.status_code == 200 and tomorrow.status_code == 200
    assert tomorrow.json()["data"]["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_OK) == Decimal("7.600")
    assert transaction_count("5") == 2


def test_transaction_id_reused_another_day_with_subscription(client):
    pay(client, transaction_id="5", occurred_at="2026-09-30T18:30:00Z")
    assert pay(client, transaction_id="5", occurred_at="2026-10-01T18:30:00Z").json()["data"]["reason_code"] == "VALID_SUBSCRIPTION"


def test_duplicate_transaction_is_rejected_and_not_debited_twice(client):
    assert pay(client, transaction_id="TRX-DUP", card_tag=CARD_OK).status_code == 200
    second = pay(client, transaction_id="TRX-DUP", card_tag=CARD_OK)
    assert second.status_code == 409
    body = second.json()
    assert body["success"] is False
    assert body["error"]["code"] == "DUPLICATE_TRANSACTION"
    assert body["error"]["details"]["status"] == "APPROVED"
    assert body["error"]["details"]["balance_after"] == pytest.approx(8.8)
    assert balance_of(CARD_OK) == Decimal("8.800")
    assert transaction_count("TRX-DUP") == 1


def test_retry_with_a_different_time_is_still_never_debited_twice(client):
    pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:30:00Z")
    again = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:33:00Z")
    assert again.status_code == 200
    assert again.json()["data"]["reason_code"] == "TRIP_ALREADY_VALIDATED"
    assert balance_of(CARD_OK) == Decimal("8.800")


def test_same_instant_in_another_timezone_is_the_same_scan(client):
    pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:30:00Z")
    again = pay(client, transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T19:30:00+01:00")
    assert again.status_code == 409


def test_same_identity_with_a_different_card_is_already_processed(client):
    pay(client, transaction_id="TRX-X", card_tag=CARD_OK)
    response = pay(client, transaction_id="TRX-X", card_tag=CARD_LOW)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSACTION_ALREADY_PROCESSED"
    assert balance_of(CARD_LOW) == Decimal("0.300")


def test_same_identity_with_a_different_line_is_already_processed(client):
    pay(client, transaction_id="TRX-X", card_tag=CARD_OK)
    response = pay(client, transaction_id="TRX-X", card_tag=CARD_OK, line_number="22B")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSACTION_ALREADY_PROCESSED"


def test_declined_transaction_is_also_idempotent(client):
    pay(client, transaction_id="TRX-D", card_tag=CARD_LOW)
    response = pay(client, transaction_id="TRX-D", card_tag=CARD_LOW)
    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "DECLINED"


# ---------------------------------------------------------------- validations

def test_unknown_line_returns_400(client):
    response = pay(client, line_number="999X")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_LINE"
    assert balance_of(CARD_SUB) == Decimal("10.000")


def test_old_field_route_id_is_no_longer_accepted(client):
    payload = payment_payload()
    del payload["line_number"]
    payload["route_id"] = "ROUTE-001"
    response = client.post(PAYMENTS_URL, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "tag", ["12345", "12345678901", "12345abcde", "1258 46585", "", 1258465854, "١٢٣٤٥٦٧٨٩٠"]
)
def test_card_tag_must_be_exactly_10_digits_as_text(client, tag):
    response = pay(client, card_tag=tag)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_leading_zeros_are_kept(client):
    assert pay(client, card_tag="0000000000").status_code == 404  # format valide, carte inconnue


def test_missing_field_returns_422_with_uniform_format(client):
    payload = payment_payload()
    del payload["card_tag"]
    response = client.post(PAYMENTS_URL, json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- états de carte

@pytest.mark.parametrize(
    "card, reason",
    [
        (CARD_BLOCKED, "CARD_BLOCKED"),
        (CARD_EXPIRED, "CARD_EXPIRED"),
        (CARD_LOST, "CARD_LOST"),
        (CARD_REPLACED, "CARD_REPLACED"),
        (CARD_INACTIVE, "CARD_NOT_ACTIVE"),
    ],
)
def test_card_that_is_not_active_is_declined_with_its_own_reason(client, card, reason):
    data = pay(client, card_tag=card).json()["data"]
    assert (data["status"], data["reason_code"]) == ("DECLINED", reason)
    assert balance_of(card) == Decimal("10.000")


def test_only_the_active_card_of_a_user_with_card_history_can_travel(client):
    assert pay(client, transaction_id="A", card_tag=CARD_LOST).json()["data"]["reason_code"] == "CARD_LOST"
    assert pay(client, transaction_id="B", card_tag=CARD_REPLACED).json()["data"]["reason_code"] == "CARD_REPLACED"
    assert pay(client, transaction_id="C", card_tag=CARD_RIM_ACTIVE).json()["data"]["reason_code"] == "BALANCE_DEBITED"


# ---------------------------------------------------------------- catégorie Handicapé : gratuité sur toutes les lignes

@pytest.mark.parametrize("line", ["22A", "28", "52A", "13C"])  # 28, 52A, 13C : sans tarif au trajet ni dans l'abonnement
def test_disabled_category_travels_free_on_any_line(client, line):
    response = pay(client, card_tag=CARD_FREE, line_number=line)
    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["status"], data["payment_method"], data["reason_code"]) == ("APPROVED", "SUBSCRIPTION", "FREE_TRAVEL_CATEGORY")
    assert data["amount"] == 0.0
    assert data["message"] == "Voyage gratuit pour cette catégorie d'abonné."
    assert balance_of(CARD_FREE) == Decimal("10.000")


def test_free_category_still_follows_the_trip_rule(client):
    pay(client, transaction_id="A-1", card_tag=CARD_FREE)
    again = pay(client, transaction_id="A-2", card_tag=CARD_FREE).json()["data"]
    assert again["reason_code"] == "TRIP_ALREADY_VALIDATED"


def test_free_category_does_not_apply_to_an_unknown_line(client):
    assert pay(client, card_tag=CARD_FREE, line_number="999X").status_code == 400


# ---------------------------------------------------------------- une carte, plusieurs abonnements (exemple Ahmad)

@pytest.mark.parametrize("line", ["13C", "16", "52A"])
def test_card_with_two_subscriptions_is_covered_on_the_lines_of_both(client, line):
    data = pay(client, card_tag=CARD_AHMAD, line_number=line).json()["data"]
    assert (data["status"], data["reason_code"]) == ("APPROVED", "VALID_SUBSCRIPTION")
    assert balance_of(CARD_AHMAD) == Decimal("10.000")


def test_card_with_two_subscriptions_pays_the_balance_outside_their_lines(client):
    data = pay(client, card_tag=CARD_AHMAD, line_number="22A").json()["data"]
    assert data["reason_code"] == "BALANCE_DEBITED"
    assert balance_of(CARD_AHMAD) == Decimal("8.800")
