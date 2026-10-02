"""Schémas : synchronisation offline."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.constants import PaymentMethod, ReasonCode, TransactionStatus
from app.schemas.transaction import Money


class SyncTransactionItem(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=64)
    card_token: str = Field(min_length=1, max_length=128)
    vehicle_id: str = Field(min_length=1, max_length=64)
    route_id: str = Field(min_length=1, max_length=64)
    fare: Decimal
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    occurred_at: datetime


class SyncRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    transactions: list[SyncTransactionItem] = Field(min_length=1, max_length=1000)


class SyncItemResult(BaseModel):
    transaction_id: str
    status: TransactionStatus
    reason_code: ReasonCode
    message: str | None = None
    payment_method: PaymentMethod | None = None
    amount: Money | None = None
    currency: str | None = None
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
