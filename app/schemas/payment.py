"""Schémas de requête : paiement / validation temps réel."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "transaction_id": "SCANNER-001-1788719400-0001",
                    "card_tag": "1258465854",
                    "device_id": "SCANNER-001",
                    "vehicle_id": "BUS-001",
                    "route_id": "ROUTE-001",
                    "fare": 0.8,
                    "occurred_at": "2026-09-30T18:30:00Z",
                }
            ]
        }
    )

    transaction_id: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "Identifiant du scan, généré par le SCANNER. Un scan est identifié par (device_id, transaction_id, occurred_at) : "
            "deux scanners, ou deux jours différents, peuvent réutiliser la même valeur sans conflit. "
            "Pour RENVOYER le même scan (retry), renvoyer exactement le même transaction_id ET le même occurred_at."
        ),
    )
    card_tag: str = Field(
        pattern=r"^[0-9]{10}$",
        description="Numéro de la carte : exactement 10 chiffres, envoyé comme TEXTE entre guillemets (ex. \"1258465854\").",
    )
    device_id: str = Field(min_length=1, max_length=64, description="Identifiant unique du scanner.")
    vehicle_id: str = Field(min_length=1, max_length=64, description="Identifiant du véhicule (bus, train...).")
    route_id: str = Field(min_length=1, max_length=64, description="Code de la ligne (ex. ROUTE-001).")
    fare: Decimal = Field(description="Tarif du voyage (> 0, 3 décimales max). INVALID_FARE sinon.")
    occurred_at: datetime = Field(description="Date/heure du scan (ISO 8601, UTC recommandé, ex. 2026-09-30T18:30:00Z).")
