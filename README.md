# Scanner Transport — Backend de test (MOCK)

Backend **de test** permettant à un développeur IoT de tester les APIs d'un scanner de transport public.

- ❌ Aucun vrai paiement (ni Stripe, ni bancaire, ni TPE) — le « paiement » est **simulé** en base.
- ❌ Aucun vrai lecteur RFID/NFC — le scanner envoie simplement un `card_token`.
- ✅ APIs REST documentées (Swagger), testables via Swagger / Postman / curl.

Stack : Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL 16, Alembic, Docker, pytest, httpx.

## 1. Installation

Prérequis : Docker + Docker Compose. (Pour lancer sans Docker : Python 3.12+ et un PostgreSQL.)

```bash
git clone <ce-projet> && cd scanner-mock-backend
```

## 2. Lancement avec Docker

```bash
docker compose up --build
```

Au démarrage, le conteneur `api` exécute automatiquement : migrations Alembic → création des données de test → serveur.

## 3. Swagger

- Swagger UI : <http://localhost:8000/docs>
- OpenAPI JSON : <http://localhost:8000/openapi.json>
- Health check : <http://localhost:8000/health> → `{"status": "ok"}`

Chaque endpoint de `/docs` propose des **exemples prêts à envoyer** (menu « Examples » du corps de requête), les réponses possibles et les erreurs.

## 4. Données de test

| Carte | Statut | Solde | Abonnement | Résultat attendu (fare = 0.800) |
|---|---|---|---|---|
| `CARD-TEST-001` | ACTIVE | 10.000 | SUB-001 → `ROUTE-001` | ROUTE-001 → `APPROVED / VALID_SUBSCRIPTION` (solde inchangé) ; ROUTE-002 → `BALANCE_DEBITED` |
| `CARD-TEST-002` | ACTIVE | 0.300 | aucun | `DECLINED / INSUFFICIENT_BALANCE` |
| `CARD-TEST-003` | ACTIVE | 10.000 | aucun | `APPROVED / BALANCE_DEBITED` |
| `CARD-TEST-004` | **BLOCKED** | 10.000 | aucun | `DECLINED / CARD_BLOCKED` |
| `CARD-TEST-005` | ACTIVE | 10.000 | SUB-002 → `ROUTE-003` | ROUTE-003 → `VALID_SUBSCRIPTION` ; ROUTE-001 → `BALANCE_DEBITED` |
| `CARD-TEST-006` *(bonus)* | **EXPIRED** | 10.000 | aucun | `DECLINED / CARD_EXPIRED` |
| `CARD-TEST-007` *(bonus)* | ACTIVE | 10.000 | SUB-EXPIRED (périmé) | `BALANCE_DEBITED` (abonnement non valide) |

Lignes : `ROUTE-001`, `ROUTE-002`, `ROUTE-003`. Toute autre ligne → `INVALID_ROUTE`. Devise : `TND`.

**Remettre les données à zéro** (soldes initiaux + purge des transactions) :

```bash
docker compose exec api python -m app.seed --reset
```

## 5. Exemples de requêtes

**Abonnement valide**
```bash
curl -X POST http://localhost:8000/api/v1/scanner/payments -H "Content-Type: application/json" -d '{
  "transaction_id": "TRX-000001", "card_token": "CARD-TEST-001", "device_id": "SCANNER-001",
  "vehicle_id": "BUS-001", "route_id": "ROUTE-001", "fare": 0.800, "currency": "TND",
  "occurred_at": "2026-09-30T18:30:00Z"}'
```
```json
{"success": true, "data": {"transaction_id": "TRX-000001", "status": "APPROVED", "payment_method": "SUBSCRIPTION",
 "reason_code": "VALID_SUBSCRIPTION", "message": "Voyage couvert par l'abonnement.", "amount": 0.0, "currency": "TND"}}
```

**Débit du solde** (`CARD-TEST-003`)
```json
{"success": true, "data": {"transaction_id": "TRX-000002", "status": "APPROVED", "payment_method": "CARD_BALANCE",
 "reason_code": "BALANCE_DEBITED", "message": "Paiement accepté.", "amount": 0.8, "currency": "TND",
 "balance_before": 10.0, "balance_after": 9.2}}
```

**Solde insuffisant** (`CARD-TEST-002`) — HTTP 200, `DECLINED`
```json
{"success": true, "data": {"transaction_id": "TRX-000003", "status": "DECLINED", "payment_method": null,
 "reason_code": "INSUFFICIENT_BALANCE", "message": "Solde insuffisant.", "amount": 0.8, "currency": "TND", "balance": 0.3}}
```

**Carte inconnue** — HTTP 404
```json
{"success": false, "error": {"code": "CARD_NOT_FOUND", "message": "Carte introuvable."}}
```

**Synchronisation offline**
```bash
curl -X POST http://localhost:8000/api/v1/scanner/sync/transactions -H "Content-Type: application/json" -d '{
  "device_id": "SCANNER-001",
  "transactions": [
    {"transaction_id": "OFFLINE-000001", "card_token": "CARD-TEST-001", "vehicle_id": "BUS-001",
     "route_id": "ROUTE-001", "fare": 0.800, "currency": "TND", "occurred_at": "2026-09-30T18:30:00Z"},
    {"transaction_id": "OFFLINE-000002", "card_token": "CARD-TEST-002", "vehicle_id": "BUS-001",
     "route_id": "ROUTE-002", "fare": 0.800, "currency": "TND", "occurred_at": "2026-09-30T18:31:00Z"},
    {"transaction_id": "OFFLINE-000001", "card_token": "CARD-TEST-001", "vehicle_id": "BUS-001",
     "route_id": "ROUTE-001", "fare": 0.800, "currency": "TND", "occurred_at": "2026-09-30T18:30:00Z"}
  ]}'
```

## 6. Logique de paiement

Pour chaque transaction, dans cet ordre (`app/services/payment_service.py`) :

1. `transaction_id` déjà connu → `DUPLICATE_TRANSACTION` (rien n'est retraité).
2. Carte introuvable → `CARD_NOT_FOUND` (HTTP 404).
3. Tarif (≤ 0, > 3 décimales, > 1000), devise ≠ devise de la carte → `INVALID_FARE` (400) ; ligne inconnue/inactive → `INVALID_ROUTE` (400).
4. Carte `BLOCKED` → `DECLINED / CARD_BLOCKED` ; `EXPIRED` → `DECLINED / CARD_EXPIRED`.
5. Abonnement valide pour la ligne → `APPROVED / VALID_SUBSCRIPTION`.
6. Sinon solde suffisant → débit → `APPROVED / BALANCE_DEBITED`.
7. Sinon → `DECLINED / INSUFFICIENT_BALANCE`.

**Convention HTTP :** un refus métier (solde insuffisant, carte bloquée/expirée) est un **HTTP 200** avec `status = DECLINED`.
Les erreurs de requête/d'identification sont des codes HTTP d'erreur (400, 404, 409, 422, 500) au format uniforme :
`{"success": false, "error": {"code": "...", "message": "..."}}`.

| Code | HTTP (`/payments`) |
|---|---|
| `VALID_SUBSCRIPTION`, `BALANCE_DEBITED` | 200 APPROVED |
| `INSUFFICIENT_BALANCE`, `CARD_BLOCKED`, `CARD_EXPIRED` | 200 DECLINED |
| `CARD_NOT_FOUND` | 404 |
| `INVALID_ROUTE`, `INVALID_FARE` | 400 |
| `DUPLICATE_TRANSACTION`, `TRANSACTION_ALREADY_PROCESSED` | 409 |
| *(champ manquant / mauvais type)* `VALIDATION_ERROR` | 422 |
| `INTERNAL_ERROR` | 500 |

## 7. Logique abonnement

Une carte est couverte si elle possède un `CardSubscription` **actif**, dont la période contient `occurred_at`
(`valid_from ≤ occurred_at ≤ valid_until`), lié à un `Subscription` **actif** qui couvre la **ligne** demandée
(table `subscription_routes`). Dans ce cas : voyage autorisé, `amount = 0`, **aucun débit**.
Un abonnement valable pour une autre ligne ne couvre pas le voyage : on retombe sur le solde.

## 8. Logique solde

`balance_after = balance_before − fare`. Le solde ne peut jamais devenir négatif (contrainte `CHECK` en base + vérification).
Un refus pour solde insuffisant ne modifie pas le solde. Les transactions refusées sont enregistrées.
La réponse contient `balance_before` / `balance_after` (débit) ou `balance` (solde insuffisant).

## 9. Synchronisation offline

`POST /api/v1/scanner/sync/transactions` traite le lot **dans l'ordre**, transaction par transaction, avec **le même
`PaymentService.process_transaction`** que `/payments` (la logique n'est pas dupliquée). Le HTTP 200 est renvoyé
pour tout lot valide ; le détail est dans `data.results`. Une erreur sur un élément (carte inconnue, ligne invalide…)
n'interrompt pas les suivants : l'élément est renvoyé `DECLINED` avec son `reason_code`.

Compteurs : `total` = reçues ; `processed` = `approved` + `declined` (hors doublons) ; `duplicates` = doublons
(`DUPLICATE_TRANSACTION` et `TRANSACTION_ALREADY_PROCESSED`). Un doublon contient aussi `original_status` /
`original_reason_code` (résultat du traitement initial).

## 10. Idempotence

- `transactions.transaction_id` a une **contrainte UNIQUE** en base.
- Renvoyer le même `transaction_id` ne débite **jamais** une seconde fois : `/payments` répond **409 `DUPLICATE_TRANSACTION`**
  (avec le résultat initial dans `error.details`), `/sync/transactions` renvoie l'élément en `DUPLICATE_TRANSACTION`.
- Même `transaction_id` mais carte / ligne / tarif différents → `TRANSACTION_ALREADY_PROCESSED`.
- **Concurrence** : dans une seule transaction PostgreSQL, la carte est verrouillée (`SELECT … FOR UPDATE`), le doublon est
  re-vérifié sous verrou, puis débit + insertion sont commités ensemble. Si deux requêtes avec le même `transaction_id`
  passent quand même simultanément, la contrainte UNIQUE fait échouer la seconde (`IntegrityError`), qui est annulée
  et convertie en doublon.

## Tests

```bash
pip install -r requirements.txt
pytest                      # SQLite en mémoire (rapide)
```

Avec PostgreSQL (verrous réels + tests de concurrence dans `tests/test_concurrency.py`) — utilisez une base dédiée,
elle est vidée avant chaque test :

```bash
docker compose up -d db
TEST_DATABASE_URL=postgresql+psycopg://scanner:scanner@localhost:5433/scanner_mock pytest
```

## Lancement sans Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # adapter DATABASE_URL
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload
```

## Structure

```
app/main.py            création de l'app, routers, middlewares, handlers d'erreurs (aucune logique métier)
app/routers/           health, payments, sync (aucune logique métier)
app/schemas/           modèles Pydantic requests/responses
app/models/            entités SQLAlchemy
app/repositories/      accès aux données
app/services/          PaymentService (toute la logique métier)
app/dependencies/      session DB + injection du service
app/core/              config, exceptions, constantes (codes métier, messages)
app/seed.py            données de test
alembic/               migrations
tests/                 pytest + httpx
```
