"""Schémas de réponse : résultat d'une transaction et enveloppe d'erreur."""
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.core.constants import PaymentMethod, ReasonCode, TransactionStatus

# Les montants sont sérialisés en nombres JSON (et non en chaînes).
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


class PaymentData(BaseModel):
    transaction_id: str
    status: TransactionStatus
    payment_method: PaymentMethod | None = Field(None, description="SUBSCRIPTION, CARD_BALANCE ou null si refusé.")
    reason_code: ReasonCode
    message: str
    amount: Money = Field(description="Montant débité (0 pour un abonnement) ou tarif demandé si refusé.")
    balance_before: Money | None = Field(None, description="Présent uniquement si le solde a été débité.")
    balance_after: Money | None = Field(None, description="Présent uniquement si le solde a été débité.")
    balance: Money | None = Field(None, description="Présent uniquement pour INSUFFICIENT_BALANCE (solde inchangé).")


class PaymentResponse(BaseModel):
    success: bool = True
    data: PaymentData


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = Field(None, description="Informations complémentaires (ex. résultat initial pour un doublon).")


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"success": False, "error": {"code": "CARD_NOT_FOUND", "message": "Carte introuvable."}}]}
    )

    success: bool = False
    error: ErrorDetail
