from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Vérifier que le backend est disponible")
def health() -> HealthResponse:
    """Retourne `{"status": "ok"}` si le backend répond."""
    return HealthResponse(status="ok")
