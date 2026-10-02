from fastapi import APIRouter, Body, Depends

from app.dependencies.services import get_payment_service
from app.schemas.sync import SyncData, SyncItemResult, SyncRequest, SyncResponse
from app.schemas.transaction import ErrorResponse
from app.services.payment_service import PaymentService, TransactionCommand

router = APIRouter(prefix="/api/v1/scanner", tags=["Scanner"])

SYNC_EXAMPLES = {
    "lot_offline": {
        "summary": "Lot de 3 transactions (la 3e est un doublon de la 1re)",
        "value": {
            "device_id": "SCANNER-001",
            "transactions": [
                {"transaction_id": "OFFLINE-000001", "card_token": "CARD-TEST-001", "vehicle_id": "BUS-001",
                 "route_id": "ROUTE-001", "fare": 0.8, "currency": "TND", "occurred_at": "2026-09-30T18:30:00Z"},
                {"transaction_id": "OFFLINE-000002", "card_token": "CARD-TEST-002", "vehicle_id": "BUS-001",
                 "route_id": "ROUTE-002", "fare": 0.8, "currency": "TND", "occurred_at": "2026-09-30T18:31:00Z"},
                {"transaction_id": "OFFLINE-000001", "card_token": "CARD-TEST-001", "vehicle_id": "BUS-001",
                 "route_id": "ROUTE-001", "fare": 0.8, "currency": "TND", "occurred_at": "2026-09-30T18:30:00Z"},
            ],
        },
    }
}

SYNC_RESPONSES = {
    200: {
        "description": (
            "Lot traité. Le HTTP 200 est toujours renvoyé si le lot est valide : le résultat de chaque "
            "transaction est dans `data.results` (APPROVED / DECLINED + reason_code)."
        ),
        "content": {"application/json": {"examples": {"lot": {"value": {
            "success": True,
            "data": {
                "device_id": "SCANNER-001", "total": 3, "processed": 2, "approved": 1, "declined": 1, "duplicates": 1,
                "results": [
                    {"transaction_id": "OFFLINE-000001", "status": "APPROVED", "reason_code": "VALID_SUBSCRIPTION"},
                    {"transaction_id": "OFFLINE-000002", "status": "DECLINED", "reason_code": "INSUFFICIENT_BALANCE"},
                    {"transaction_id": "OFFLINE-000001", "status": "DECLINED", "reason_code": "DUPLICATE_TRANSACTION",
                     "original_status": "APPROVED", "original_reason_code": "VALID_SUBSCRIPTION"},
                ],
            },
        }}}}},
    },
    422: {"model": ErrorResponse, "description": "Corps invalide (liste vide, > 1000 transactions, champ manquant...)."},
    500: {"model": ErrorResponse, "description": "INTERNAL_ERROR."},
}


@router.post(
    "/sync/transactions",
    response_model=SyncResponse,
    response_model_exclude_unset=True,
    summary="Synchronisation des transactions offline",
    responses=SYNC_RESPONSES,
)
def sync_transactions(
    body: SyncRequest = Body(..., openapi_examples=SYNC_EXAMPLES),
    service: PaymentService = Depends(get_payment_service),
) -> SyncResponse:
    """Traite, dans l'ordre, un lot de transactions stockées hors ligne par le scanner.

    Chaque transaction passe par **le même `PaymentService`** que `POST /payments`.
    Un `transaction_id` déjà connu n'est jamais retraité : il est renvoyé en
    `DUPLICATE_TRANSACTION` (avec le statut initial dans `original_status`).
    Une erreur sur une transaction (carte inconnue, ligne invalide...) n'empêche pas les suivantes.
    """
    commands = [
        TransactionCommand(device_id=body.device_id, **item.model_dump()) for item in body.transactions
    ]
    batch = service.process_batch(body.device_id, commands)
    return SyncResponse(
        success=True,
        data=SyncData(
            device_id=batch.device_id,
            total=batch.total,
            processed=batch.processed,
            approved=batch.approved,
            declined=batch.declined,
            duplicates=batch.duplicates,
            results=[
                SyncItemResult(**r.as_dict(keep_null_payment_method=False)) for r in batch.results
            ],
        ),
    )
