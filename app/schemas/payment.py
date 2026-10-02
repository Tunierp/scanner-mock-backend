"""Schémas de requête : paiement / validation temps réel."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "transaction_id": "TRX-000001",
                    "card_token": "CARD-TEST-001",
                    "device_id": "SCANNER-001",
                    "vehicle_id": "BUS-001",
                    "route_id": "ROUTE-001",
                    "fare": 0.8,
                    "currency": "TND",
                    "occurred_at": "2026-09-30T18:30:00Z",
                }
            ]
        }
    )

    transaction_id: str = Field(min_length=1, max_length=64, description="Identifiant unique généré par le scanner (clé d'idempotence).")
    card_token: str = Field(min_length=1, max_length=128, description="Jeton de la carte lue.")
    device_id: str = Field(min_length=1, max_length=64, description="Identifiant du scanner.")
    vehicle_id: str = Field(min_length=1, max_length=64, description="Identifiant du véhicule.")
    route_id: str = Field(min_length=1, max_length=64, description="Code de la ligne (ex. ROUTE-001).")
    fare: Decimal = Field(description="Tarif du voyage (> 0, 3 décimales max). Validé par le service : INVALID_FARE sinon.")
    currency: str = Field(pattern=r"^[A-Za-z]{3}$", description="Devise ISO 4217 (ex. TND).")
    occurred_at: datetime = Field(description="Date/heure du voyage (ISO 8601, UTC recommandé).")
