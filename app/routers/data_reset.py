"""⚠ API TEMPORAIRE — réinitialiser les données de test sans accès au serveur.

Cet endpoint est destructif et sera SUPPRIMÉ (voir README, « Retirer l'API de réinitialisation »). Pour le retirer :
supprimer ce fichier, `app/services/data_reset_service.py`, `app/schemas/data_reset.py`, `get_data_reset_service` dans
`app/dependencies/services.py`, l'inclusion du routeur dans `app/main.py`, et les réglages TEST_DATA_RESET_* dans `app/core/config.py`.
Pour le désactiver sans rien supprimer : TEST_DATA_RESET_ENABLED=false (l'endpoint n'est alors plus enregistré).
"""
import logging
import secrets

from fastapi import APIRouter, Depends, Header, Request

from app.core.config import Settings, get_settings
from app.core.exceptions import ResetForbiddenError
from app.dependencies.services import get_data_reset_service
from app.schemas.data_reset import CardStateOut, ResetData, ResetResponse
from app.schemas.transaction import ErrorResponse
from app.services.data_reset_service import DataResetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/test-data", tags=["⚠ Données de test (API TEMPORAIRE)"])


@router.post(
    "/reset",
    response_model=ResetResponse,
    summary="Réinitialiser les données de test (API temporaire)",
    responses={
        403: {"model": ErrorResponse, "description": "RESET_FORBIDDEN : le serveur exige l'en-tête `X-Reset-Token` et il est absent ou invalide."},
        500: {"model": ErrorResponse, "description": "INTERNAL_ERROR : rien n'a été modifié."},
    },
)
def reset_test_data(
    request: Request,
    x_reset_token: str | None = Header(None, description="Requis seulement si le serveur définit TEST_DATA_RESET_TOKEN."),
    settings: Settings = Depends(get_settings),
    service: DataResetService = Depends(get_data_reset_service),
) -> ResetResponse:
    """⚠ **API temporaire, destructive, qui sera supprimée.** Équivaut à `python -m app.seed --reset` :

    * **supprime toutes les transactions** (les `transaction_id` peuvent être réutilisés ensuite) ;
    * remet les **cartes de test** à leur solde et à leur état initiaux (`1000000001`…, `1236547895`, `1258465854`/`5`) ;
    * recrée ce qui manque des données de test (lignes, liaisons, catégories, abonnements…).

    Les données ajoutées en dehors du seed sont conservées. Aucun corps de requête n'est nécessaire.
    """
    expected = settings.test_data_reset_token
    if expected and not (x_reset_token and secrets.compare_digest(x_reset_token, expected)):
        logger.warning("Réinitialisation refusée (jeton invalide) depuis %s", request.client.host if request.client else "?")
        raise ResetForbiddenError()
    logger.warning("Réinitialisation des données de test demandée depuis %s", request.client.host if request.client else "?")
    result = service.reset()
    return ResetResponse(success=True, data=ResetData(
        message="Données de test réinitialisées.", deleted_transactions=result.deleted_transactions,
        cards=[CardStateOut(card_tag=c.card_tag, status=c.status, balance=c.balance) for c in result.cards]))
