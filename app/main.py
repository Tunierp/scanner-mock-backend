import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.routers import data_reset, health, payments, sync  # data_reset : TEMPORAIRE

DESCRIPTION = """
**Backend de TEST (MOCK)** pour le développeur IoT : aucun vrai paiement, aucun vrai lecteur RFID/NFC.

Logique : abonnement valide pour la ligne → voyage gratuit ; sinon débit du solde ; sinon refus.
Cartes de test : `1000000001` à `1000000012`, `1236547895`, `1258465854`, `1258465855` (voir le README).

⚠ `POST /api/v1/test-data/reset` (API **temporaire**) remet les données de test à zéro.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(title=settings.app_name, version=settings.app_version, description=DESCRIPTION)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(payments.router)
    app.include_router(sync.router)
    if settings.test_data_reset_enabled:  # TEMPORAIRE : à supprimer avec l'API de réinitialisation
        app.include_router(data_reset.router)
    return app


app = create_app()
