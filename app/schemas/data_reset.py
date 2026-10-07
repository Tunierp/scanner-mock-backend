"""⚠ TEMPORAIRE — schémas de l'API de réinitialisation des données de test."""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.transaction import Money


class CardStateOut(BaseModel):
    card_tag: str
    status: str
    balance: Money


class ResetData(BaseModel):
    message: str
    deleted_transactions: int = Field(description="Nombre de transactions supprimées.")
    cards: list[CardStateOut] = Field(description="État des cartes de test après la réinitialisation.")


class ResetResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "success": True,
        "data": {"message": "Données de test réinitialisées.", "deleted_transactions": 12,
                 "cards": [{"card_tag": "1000000001", "status": "ACTIVE", "balance": 10.0}]},
    }]})
    success: bool = True
    data: ResetData
