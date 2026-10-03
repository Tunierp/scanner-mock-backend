from decimal import Decimal

import pytest

from tests.conftest import (
    CARD_A, CARD_B, CARD_BLOCKED, CARD_LOW, CARD_OK, CARD_SUB, CARD_SUB_R3, CARD_UNKNOWN, PAYMENTS_URL, SYNC_URL,
    balance_of, payment_payload, sync_item, transaction_count,
)


def sync(client, *items, device_id="SCANNER-001"):
    return client.post(SYNC_URL, json={"device_id": device_id, "transactions": list(items)})


def test_sync_multiple_transactions_with_duplicate(client):
    response = sync(
        client,
        sync_item(transaction_id="OFFLINE-000001", card_tag=CARD_SUB, route_id="ROUTE-001"),
        sync_item(transaction_id="OFFLINE-000002", card_tag=CARD_LOW, route_id="ROUTE-002"),
        sync_item(transaction_id="OFFLINE-000001", card_tag=CARD_SUB, route_id="ROUTE-001"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert (data["device_id"], data["total"], data["processed"]) == ("SCANNER-001", 3, 2)
    assert (data["approved"], data["declined"], data["duplicates"]) == (1, 1, 1)
    results = [(r["transaction_id"], r["status"], r["reason_code"]) for r in data["results"]]
    assert results == [
        ("OFFLINE-000001", "APPROVED", "VALID_SUBSCRIPTION"),
        ("OFFLINE-000002", "DECLINED", "INSUFFICIENT_BALANCE"),
        ("OFFLINE-000001", "DECLINED", "DUPLICATE_TRANSACTION"),
    ]
    assert data["results"][2]["original_status"] == "APPROVED"
    assert balance_of(CARD_LOW) == Decimal("0.300")


def test_sync_debits_balance_cards(client):
    result = sync(client, sync_item(transaction_id="O-1", card_tag=CARD_OK)).json()["data"]["results"][0]
    assert (result["status"], result["reason_code"]) == ("APPROVED", "BALANCE_DEBITED")
    assert result["balance_before"] == pytest.approx(10.0)
    assert result["balance_after"] == pytest.approx(9.2)
    assert balance_of(CARD_OK) == Decimal("9.200")


def test_sync_with_transactions_already_processed_online(client):
    client.post(PAYMENTS_URL, json=payment_payload(transaction_id="TRX-ONLINE", card_tag=CARD_OK))
    response = sync(
        client,
        sync_item(transaction_id="TRX-ONLINE", card_tag=CARD_OK),
        sync_item(transaction_id="O-NEW", card_tag=CARD_OK, vehicle_id="BUS-002"),
    )
    data = response.json()["data"]
    assert data["duplicates"] == 1 and data["approved"] == 1 and data["processed"] == 1
    assert data["results"][0]["reason_code"] == "DUPLICATE_TRANSACTION"
    assert balance_of(CARD_OK) == Decimal("8.400")  # 2 débits seulement


def test_offline_transaction_never_debited_twice(client):
    item = sync_item(transaction_id="OFFLINE-000001", card_tag=CARD_OK)
    for _ in range(3):  # le scanner renvoie le même lot (problème réseau)
        assert sync(client, item).status_code == 200
    assert balance_of(CARD_OK) == Decimal("9.200")
    assert transaction_count("OFFLINE-000001") == 1


def test_sync_continues_after_unknown_card_or_invalid_route(client):
    response = sync(
        client,
        sync_item(transaction_id="O-1", card_tag=CARD_UNKNOWN),
        sync_item(transaction_id="O-2", card_tag=CARD_OK, route_id="ROUTE-999"),
        sync_item(transaction_id="O-3", card_tag=CARD_OK),
    )
    assert response.status_code == 200
    codes = [r["reason_code"] for r in response.json()["data"]["results"]]
    assert codes == ["CARD_NOT_FOUND", "INVALID_ROUTE", "BALANCE_DEBITED"]
    assert response.json()["data"]["approved"] == 1


def test_sync_same_transaction_id_from_two_scanners_is_not_a_duplicate(client):
    first = sync(client, sync_item(transaction_id="T01", card_tag=CARD_A), device_id="SCANNER-001")
    second = sync(
        client,
        sync_item(transaction_id="T01", card_tag=CARD_B, vehicle_id="BUS-002", route_id="ROUTE-002"),
        device_id="SCANNER-002",
    )
    assert first.json()["data"]["approved"] == 1
    assert second.json()["data"]["approved"] == 1
    assert second.json()["data"]["duplicates"] == 0


def test_sync_transaction_id_reused_another_day_is_processed(client):
    first = sync(client, sync_item(transaction_id="5", card_tag=CARD_OK, occurred_at="2026-09-30T18:30:00Z"))
    second = sync(client, sync_item(transaction_id="5", card_tag=CARD_OK, occurred_at="2026-10-01T18:30:00Z"))
    assert first.json()["data"]["approved"] == 1
    assert second.json()["data"]["approved"] == 1 and second.json()["data"]["duplicates"] == 0
    assert balance_of(CARD_OK) == Decimal("8.400")


def test_sync_double_scan_in_same_batch_is_declined(client):
    response = sync(
        client,
        sync_item(transaction_id="O-1", card_tag=CARD_OK),
        sync_item(transaction_id="O-2", card_tag=CARD_OK, occurred_at="2026-09-30T18:31:00Z"),
    )
    data = response.json()["data"]
    assert [r["reason_code"] for r in data["results"]] == ["BALANCE_DEBITED", "TRIP_ALREADY_VALIDATED"]
    assert (data["approved"], data["declined"], data["duplicates"]) == (1, 1, 0)
    assert balance_of(CARD_OK) == Decimal("9.200")


def test_sync_and_payments_give_the_same_decision(client):
    scenarios = [
        (CARD_SUB, "ROUTE-001"), (CARD_SUB, "ROUTE-002"), (CARD_LOW, "ROUTE-001"),
        (CARD_BLOCKED, "ROUTE-001"), (CARD_SUB_R3, "ROUTE-003"), (CARD_SUB_R3, "ROUTE-001"),
    ]
    for i, (card, route) in enumerate(scenarios):
        online = client.post(
            PAYMENTS_URL, json=payment_payload(transaction_id=f"ON-{i}", card_tag=card, route_id=route)
        ).json()["data"]
        offline = sync(
            client, sync_item(transaction_id=f"OFF-{i}", card_tag=card, route_id=route, vehicle_id="BUS-002")
        ).json()["data"]["results"][0]
        assert (online["status"], online["reason_code"]) == (offline["status"], offline["reason_code"])


def test_sync_rejects_empty_batch(client):
    response = client.post(SYNC_URL, json={"device_id": "SCANNER-001", "transactions": []})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_sync_rejects_bad_card_tag(client):
    response = sync(client, sync_item(transaction_id="O-1", card_tag="ABC"))
    assert response.status_code == 422
