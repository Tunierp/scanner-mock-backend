import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.routers import health, payments, sync

settings = get_settings()
logging.basicConfig(level=settings.log_level)

DESCRIPTION = """
**Backend de TEST (MOCK)** pour le développeur IoT : aucun vrai paiement, aucun vrai lecteur RFID/NFC.

Logique : abonnement valide pour la ligne → voyage gratuit ; sinon débit du solde ; sinon refus.
Cartes de test : `CARD-TEST-001` à `CARD-TEST-007` (voir le README).
"""

app = FastAPI(title=settings.app_name, version=settings.app_version, description=DESCRIPTION)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
register_exception_handlers(app)

app.include_router(health.router)
app.include_router(payments.router)
app.include_router(sync.router)
