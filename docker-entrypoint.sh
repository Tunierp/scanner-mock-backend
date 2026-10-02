#!/bin/sh
set -e
echo "==> Migrations Alembic"
alembic upgrade head
echo "==> Données de test"
python -m app.seed
echo "==> Démarrage de l'API"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
