from decimal import Decimal

import pytest

from tests.conftest import PAYMENTS_URL, SYNC_URL, balance_of, payment_payload, sync_item, transaction_count


def sync(client, *items, device_id="SCANNER-001"):
    return client.post(SYNC_URL, json={"device_id": device_id, "transactions": list(items)})


# 8. sync de plusieurs transactions (exemple du cahier des charges)
def test_sync_multiple_transactions_with_duplicate(client):
    response = sync(
        client,
        sync_item(transaction_id="OFFLINE-000001", card_token="CARD-TEST-001", route_id="ROUTE-001"),
        sync_item(transaction_id="OFFLINE-000002", card_token="CARD-TEST-002", route_id="ROUTE-002"),
        sync_item(transaction_id="OFFLINE-000001", card_token="CARD-TEST-001", route_id="ROUTE-001"),
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
    assert balance_of("CARD-TEST-002") == Decimal("0.300")


def test_sync_debits_balance_cards(client):
    response = sync(client, sync_item(transaction_id="O-1", card_token="CARD-TEST-003"))
    result = response.json()["data"]["results"][0]
    assert result["status"] == "APPROVED"
    assert result["reason_code"] == "BALANCE_DEBITED"
    assert result["balance_before"] == pytest.approx(10.0)
    assert result["balance_after"] == pytest.approx(9.2)
    assert balance_of("CARD-TEST-003") == Decimal("9.200")


# 9. sync contenant des transactions déjà traitées (ici via /payments)
def test_sync_with_transactions_already_processed_online(client):
    client.post(PAYMENTS_URL, json=payment_payload(transaction_id="TRX-ONLINE", card_token="CARD-TEST-003"))
    response = sync(
        client,
        sync_item(transaction_id="TRX-ONLINE", card_token="CARD-TEST-003"),
        sync_item(transaction_id="O-NEW", card_token="CARD-TEST-003"),
    )
    data = response.json()["data"]
    assert data["duplicates"] == 1 and data["approved"] == 1 and data["processed"] == 1
    assert data["results"][0]["reason_code"] == "DUPLICATE_TRANSACTION"
    assert balance_of("CARD-TEST-003") == Decimal("8.400")  # 2 débits seulement


# 10. une transaction offline n'est jamais débitée deux fois
def test_offline_transaction_never_debited_twice(client):
    item = sync_item(transaction_id="OFFLINE-000001", card_token="CARD-TEST-003")
    for _ in range(3):  # le scanner renvoie le même lot (problème réseau)
        response = sync(client, item)
        assert response.status_code == 200
    assert balance_of("CARD-TEST-003") == Decimal("9.200")
    assert transaction_count("OFFLINE-000001") == 1


def test_sync_continues_after_unknown_card_or_invalid_route(client):
    response = sync(
        client,
        sync_item(transaction_id="O-1", card_token="CARD-UNKNOWN"),
        sync_item(transaction_id="O-2", card_token="CARD-TEST-003", route_id="ROUTE-999"),
        sync_item(transaction_id="O-3", card_token="CARD-TEST-003"),
    )
    assert response.status_code == 200
    codes = [r["reason_code"] for r in response.json()["data"]["results"]]
    assert codes == ["CARD_NOT_FOUND", "INVALID_ROUTE", "BALANCE_DEBITED"]
    assert response.json()["data"]["approved"] == 1


def test_sync_and_payments_give_the_same_decision(client):
    scenarios = [
        ("CARD-TEST-001", "ROUTE-001"), ("CARD-TEST-001", "ROUTE-002"), ("CARD-TEST-002", "ROUTE-001"),
        ("CARD-TEST-004", "ROUTE-001"), ("CARD-TEST-005", "ROUTE-003"), ("CARD-TEST-005", "ROUTE-001"),
    ]
    for i, (card, route) in enumerate(scenarios):
        online = client.post(
            PAYMENTS_URL, json=payment_payload(transaction_id=f"ON-{i}", card_token=card, route_id=route)
        ).json()["data"]
        offline = sync(client, sync_item(transaction_id=f"OFF-{i}", card_token=card, route_id=route))
        offline = offline.json()["data"]["results"][0]
        assert (online["status"], online["reason_code"]) == (offline["status"], offline["reason_code"])


def test_sync_rejects_empty_batch(client):
    response = client.post(SYNC_URL, json={"device_id": "SCANNER-001", "transactions": []})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
