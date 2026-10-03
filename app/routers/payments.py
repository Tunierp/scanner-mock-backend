from fastapi import APIRouter, Body, Depends

from app.dependencies.services import get_payment_service
from app.schemas.payment import PaymentRequest
from app.schemas.transaction import ErrorResponse, PaymentData, PaymentResponse
from app.services.payment_service import PaymentService, TransactionCommand

router = APIRouter(prefix="/api/v1/scanner", tags=["Scanner"])

_BASE = {
    "device_id": "SCANNER-001",
    "vehicle_id": "BUS-001",
    "route_id": "ROUTE-001",
    "fare": 0.8,
    "occurred_at": "2026-09-30T18:30:00Z",
}

REQUEST_EXAMPLES = {
    "abonnement_valide": {
        "summary": "Carte 1000000001 / ROUTE-001 → APPROVED (VALID_SUBSCRIPTION)",
        "value": {**_BASE, "transaction_id": "SCANNER-001-0001", "card_tag": "1000000001"},
    },
    "debit_solde": {
        "summary": "Carte 1000000003 / ROUTE-001 → APPROVED (BALANCE_DEBITED)",
        "value": {**_BASE, "transaction_id": "SCANNER-001-0002", "card_tag": "1000000003"},
    },
    "double_scan": {
        "summary": "Même carte, même bus, même ligne, NOUVEAU transaction_id → DECLINED (TRIP_ALREADY_VALIDATED)",
        "value": {**_BASE, "transaction_id": "SCANNER-001-0003", "card_tag": "1000000003"},
    },
    "solde_insuffisant": {
        "summary": "Carte 1000000002 → DECLINED (INSUFFICIENT_BALANCE)",
        "value": {**_BASE, "transaction_id": "SCANNER-001-0004", "card_tag": "1000000002"},
    },
    "carte_bloquee": {
        "summary": "Carte 1000000004 → DECLINED (CARD_BLOCKED)",
        "value": {**_BASE, "transaction_id": "SCANNER-001-0005", "card_tag": "1000000004"},
    },
    "abonnement_autre_ligne": {
        "summary": "Carte 1000000005 / ROUTE-001 → débit du solde (son abonnement couvre ROUTE-003)",
        "value": {**_BASE, "transaction_id": "SCANNER-001-0006", "card_tag": "1000000005"},
    },
    "carte_inconnue": {
        "summary": "Carte inexistante → 404 CARD_NOT_FOUND",
        "value": {**_BASE, "transaction_id": "SCANNER-001-0007", "card_tag": "9999999999"},
    },
    "bus_1": {
        "summary": "Deux bus, même transaction_id « T01 » (1/2) : scanner 001 / BUS-001",
        "value": {**_BASE, "transaction_id": "T01", "card_tag": "1258465854"},
    },
    "bus_2": {
        "summary": "Deux bus, même transaction_id « T01 » (2/2) : scanner 002 / BUS-002 → accepté aussi",
        "value": {**_BASE, "transaction_id": "T01", "card_tag": "1258465855", "device_id": "SCANNER-002",
                  "vehicle_id": "BUS-002", "route_id": "ROUTE-002"},
    },
}


def _example(status: str, reason: str, message: str, method: str | None, amount: float, **extra) -> dict:
    data = {
        "transaction_id": "SCANNER-001-0001", "status": status, "payment_method": method,
        "reason_code": reason, "message": message, "amount": amount, **extra,
    }
    return {"value": {"success": True, "data": data}}


def _error(code: str, message: str, details: dict | None = None) -> dict:
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"value": {"success": False, "error": error}}


RESPONSES = {
    200: {
        "description": "Scan traité (APPROVED ou DECLINED).",
        "content": {"application/json": {"examples": {
            "abonnement": _example("APPROVED", "VALID_SUBSCRIPTION", "Voyage couvert par l'abonnement.", "SUBSCRIPTION", 0.0),
            "solde_debite": _example("APPROVED", "BALANCE_DEBITED", "Paiement accepté.", "CARD_BALANCE", 0.8,
                                     balance_before=5.0, balance_after=4.2),
            "solde_insuffisant": _example("DECLINED", "INSUFFICIENT_BALANCE", "Solde insuffisant.", None, 0.8, balance=0.3),
            "voyage_deja_valide": _example("DECLINED", "TRIP_ALREADY_VALIDATED", "Votre voyage est déjà payé/validé.", None, 0.8),
            "carte_bloquee": _example("DECLINED", "CARD_BLOCKED", "Carte bloquée.", None, 0.8),
        }}},
    },
    400: {
        "model": ErrorResponse,
        "description": "INVALID_ROUTE (ligne inconnue/inactive) ou INVALID_FARE (tarif ≤ 0 ou plus de 3 décimales).",
        "content": {"application/json": {"examples": {
            "invalid_route": _error("INVALID_ROUTE", "Ligne invalide ou inactive."),
            "invalid_fare": _error("INVALID_FARE", "Le tarif doit être strictement positif."),
        }}},
    },
    404: {
        "model": ErrorResponse,
        "description": "CARD_NOT_FOUND : aucune carte pour ce card_tag.",
        "content": {"application/json": {"examples": {"card_not_found": _error("CARD_NOT_FOUND", "Carte introuvable.")}}},
    },
    409: {
        "model": ErrorResponse,
        "description": (
            "DUPLICATE_TRANSACTION : ce scan (même scanner, même transaction_id, même occurred_at) a déjà été traité ; rien "
            "n'est retraité, `details` contient le résultat initial. TRANSACTION_ALREADY_PROCESSED : même identité de scan mais données différentes."
        ),
        "content": {"application/json": {"examples": {
            "duplicate": _error("DUPLICATE_TRANSACTION", "Transaction déjà traitée (doublon). Le résultat initial est conservé.",
                                {"transaction_id": "SCANNER-001-0001", "status": "APPROVED", "payment_method": "CARD_BALANCE",
                                 "reason_code": "BALANCE_DEBITED", "amount": 0.8, "balance_before": 5.0, "balance_after": 4.2}),
        }}},
    },
    422: {"model": ErrorResponse, "description": "Corps invalide (champ manquant, card_tag qui n'a pas 10 chiffres...)."},
    500: {"model": ErrorResponse, "description": "INTERNAL_ERROR."},
}


@router.post(
    "/payments",
    response_model=PaymentResponse,
    response_model_exclude_unset=True,
    summary="Demande de paiement / validation d'un voyage",
    responses=RESPONSES,
)
def create_payment(
    body: PaymentRequest = Body(..., openapi_examples=REQUEST_EXAMPLES),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    """Valide un voyage pour une carte.

    1. Même carte déjà validée dans ce véhicule, sur cette ligne (même voyage) → `DECLINED / TRIP_ALREADY_VALIDATED`, aucun débit.
    2. Abonnement actif valable pour la ligne → `APPROVED / VALID_SUBSCRIPTION`, **aucun débit**.
    3. Sinon, solde suffisant → débit + `APPROVED / BALANCE_DEBITED`.
    4. Sinon → `DECLINED / INSUFFICIENT_BALANCE`, solde inchangé.

    **Renvoi d'un scan (retry réseau)** : renvoyer le même `transaction_id` ET le même `occurred_at` (heure du badge, jamais
    « maintenant ») ne débite jamais deux fois (409 `DUPLICATE_TRANSACTION`). Un `transaction_id` réutilisé un autre jour est un nouveau scan.
    Un refus métier (solde insuffisant, carte bloquée/expirée, voyage déjà validé) est un **HTTP 200** avec `status = DECLINED`.
    """
    result = service.process_transaction(TransactionCommand(**body.model_dump()))
    return PaymentResponse(success=True, data=PaymentData(**result.as_dict()))
