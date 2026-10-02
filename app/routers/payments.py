from fastapi import APIRouter, Body, Depends

from app.core.constants import ReasonCode
from app.dependencies.services import get_payment_service
from app.schemas.payment import PaymentRequest
from app.schemas.transaction import ErrorResponse, PaymentData, PaymentResponse
from app.services.payment_service import PaymentService, TransactionCommand

router = APIRouter(prefix="/api/v1/scanner", tags=["Scanner"])

_BASE = {
    "device_id": "SCANNER-001",
    "vehicle_id": "BUS-001",
    "fare": 0.8,
    "currency": "TND",
    "occurred_at": "2026-09-30T18:30:00Z",
}

REQUEST_EXAMPLES = {
    "abonnement_valide": {
        "summary": "CARD-TEST-001 / ROUTE-001 → APPROVED (VALID_SUBSCRIPTION)",
        "value": {**_BASE, "transaction_id": "TRX-000001", "card_token": "CARD-TEST-001", "route_id": "ROUTE-001"},
    },
    "debit_solde": {
        "summary": "CARD-TEST-003 / ROUTE-001 → APPROVED (BALANCE_DEBITED)",
        "value": {**_BASE, "transaction_id": "TRX-000002", "card_token": "CARD-TEST-003", "route_id": "ROUTE-001"},
    },
    "solde_insuffisant": {
        "summary": "CARD-TEST-002 → DECLINED (INSUFFICIENT_BALANCE)",
        "value": {**_BASE, "transaction_id": "TRX-000003", "card_token": "CARD-TEST-002", "route_id": "ROUTE-001"},
    },
    "carte_bloquee": {
        "summary": "CARD-TEST-004 → DECLINED (CARD_BLOCKED)",
        "value": {**_BASE, "transaction_id": "TRX-000004", "card_token": "CARD-TEST-004", "route_id": "ROUTE-001"},
    },
    "abonnement_autre_ligne": {
        "summary": "CARD-TEST-005 / ROUTE-001 → débit du solde ; ROUTE-003 → abonnement",
        "value": {**_BASE, "transaction_id": "TRX-000005", "card_token": "CARD-TEST-005", "route_id": "ROUTE-001"},
    },
    "carte_inconnue": {
        "summary": "Carte inexistante → 404 CARD_NOT_FOUND",
        "value": {**_BASE, "transaction_id": "TRX-000006", "card_token": "CARD-UNKNOWN", "route_id": "ROUTE-001"},
    },
}


def _example(status: str, reason: str, message: str, method: str | None, amount: float, **extra) -> dict:
    data = {
        "transaction_id": "TRX-000001", "status": status, "payment_method": method,
        "reason_code": reason, "message": message, "amount": amount, "currency": "TND", **extra,
    }
    return {"value": {"success": True, "data": data}}


def _error(code: str, message: str, details: dict | None = None) -> dict:
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"value": {"success": False, "error": error}}


RESPONSES = {
    200: {
        "description": "Transaction traitée (APPROVED ou DECLINED).",
        "content": {"application/json": {"examples": {
            "abonnement": _example("APPROVED", "VALID_SUBSCRIPTION", "Voyage couvert par l'abonnement.", "SUBSCRIPTION", 0.0),
            "solde_debite": _example("APPROVED", "BALANCE_DEBITED", "Paiement accepté.", "CARD_BALANCE", 0.8,
                                     balance_before=5.0, balance_after=4.2),
            "solde_insuffisant": _example("DECLINED", "INSUFFICIENT_BALANCE", "Solde insuffisant.", None, 0.8, balance=0.3),
            "carte_bloquee": _example("DECLINED", "CARD_BLOCKED", "Carte bloquée.", None, 0.8),
        }}},
    },
    400: {
        "model": ErrorResponse,
        "description": "INVALID_ROUTE (ligne inconnue/inactive) ou INVALID_FARE (tarif ≤ 0, > 3 décimales, devise incorrecte).",
        "content": {"application/json": {"examples": {
            "invalid_route": _error("INVALID_ROUTE", "Ligne invalide ou inactive."),
            "invalid_fare": _error("INVALID_FARE", "Le tarif doit être strictement positif."),
        }}},
    },
    404: {
        "model": ErrorResponse,
        "description": "CARD_NOT_FOUND : aucune carte pour ce card_token.",
        "content": {"application/json": {"examples": {"card_not_found": _error("CARD_NOT_FOUND", "Carte introuvable.")}}},
    },
    409: {
        "model": ErrorResponse,
        "description": (
            "DUPLICATE_TRANSACTION : ce transaction_id a déjà été traité (rien n'est retraité, `details` "
            "contient le résultat initial). TRANSACTION_ALREADY_PROCESSED : même transaction_id mais données différentes."
        ),
        "content": {"application/json": {"examples": {
            "duplicate": _error("DUPLICATE_TRANSACTION", "Transaction déjà traitée (doublon). Le résultat initial est conservé.",
                                {"transaction_id": "TRX-000001", "status": "APPROVED", "payment_method": "CARD_BALANCE",
                                 "reason_code": "BALANCE_DEBITED", "amount": 0.8, "balance_before": 5.0, "balance_after": 4.2}),
        }}},
    },
    422: {"model": ErrorResponse, "description": "Corps de requête invalide (champ manquant, mauvais type...)."},
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

    1. Abonnement actif valable pour la ligne → `APPROVED / VALID_SUBSCRIPTION`, **aucun débit**.
    2. Sinon, solde suffisant → débit + `APPROVED / BALANCE_DEBITED`.
    3. Sinon → `DECLINED / INSUFFICIENT_BALANCE`, solde inchangé.

    Idempotent : rejouer le même `transaction_id` ne débite jamais deux fois (409 `DUPLICATE_TRANSACTION`).
    Un refus métier (solde insuffisant, carte bloquée/expirée) est un **HTTP 200** avec `status = DECLINED`.
    """
    result = service.process_transaction(TransactionCommand(**body.model_dump()))
    return PaymentResponse(success=True, data=PaymentData(**result.as_dict()))
