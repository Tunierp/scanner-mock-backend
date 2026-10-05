"""Schémas : synchronisation offline."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import PaymentMethod, ReasonCode, TransactionStatus
from app.schemas.transaction import Money


class SyncTransactionItem(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=64)
    card_tag: str = Field(pattern=r"^[0-9]{10}$", description="10 chiffres, en texte.")
    vehicle_id: str = Field(min_length=1, max_length=64)
    line_number: str = Field(min_length=1, max_length=16, description="Numéro de la ligne (ex. 22A).")
    occurred_at: datetime


class SyncRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64, description="Scanner émetteur du lot (valable pour toutes les transactions).")
    transactions: list[SyncTransactionItem] = Field(min_length=1, max_length=1000)


class SyncItemResult(BaseModel):
    transaction_id: str
    status: TransactionStatus
    reason_code: ReasonCode
    message: str | None = None
    payment_method: PaymentMethod | None = None
    amount: Money | None = None
    balance_before: Money | None = None
    balance_after: Money | None = None
    original_status: str | None = Field(None, description="Pour un doublon : statut du traitement initial.")
    original_reason_code: str | None = Field(None, description="Pour un doublon : reason_code du traitement initial.")


class SyncData(BaseModel):
    device_id: str
    total: int = Field(description="Nombre de transactions reçues.")
    processed: int = Field(description="Transactions réellement traitées (approved + declined), hors doublons.")
    approved: int
    declined: int
    duplicates: int = Field(description="Transactions déjà connues (DUPLICATE_TRANSACTION / TRANSACTION_ALREADY_PROCESSED).")
    results: list[SyncItemResult]


class SyncResponse(BaseModel):
    success: bool = True
    data: SyncData
