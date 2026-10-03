# Scanner Transport — Backend de test (MOCK)

> **« mock » = simulé / factice.** Ce backend *imite* le vrai système (paiement, cartes, abonnements) avec des données
> fictives en base, uniquement pour que le développeur IoT puisse tester ses appels API. Aucun vrai paiement
> (ni Stripe, ni banque, ni TPE), aucun vrai lecteur RFID/NFC. Le nom `scanner_mock` (base de données) n'a aucun
> effet technique : il se change dans `DATABASE_URL`.

Stack : Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, pytest, httpx (Docker en option).

## Lancement sans Docker

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # adapter DATABASE_URL
alembic upgrade head              # crée / met à jour les tables
python -m app.seed                # données de test
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Swagger : <http://localhost:8000/docs> — Health : <http://localhost:8000/health>

Avec Docker : `docker compose up --build`.
Remise à zéro des soldes et des transactions : `python -m app.seed --reset`.

## Mise à jour depuis la version précédente

```bash
alembic upgrade head          # migrations 0002 (card_token -> card_tag) et 0003 (identité du scan)
python -m app.seed --reset    # ajoute les nouvelles cartes et remet les soldes
```

## Cartes de test

| `card_tag` | Statut | Solde | Abonnement | Résultat (tarif 0.800) |
|---|---|---|---|---|
| `1000000001` | ACTIVE | 10.000 | `ROUTE-001` | ROUTE-001 → `VALID_SUBSCRIPTION` ; ROUTE-002 → `BALANCE_DEBITED` |
| `1000000002` | ACTIVE | 0.300 | aucun | `INSUFFICIENT_BALANCE` |
| `1000000003` | ACTIVE | 10.000 | aucun | `BALANCE_DEBITED` |
| `1000000004` | BLOCKED | 10.000 | aucun | `CARD_BLOCKED` |
| `1000000005` | ACTIVE | 10.000 | `ROUTE-003` | ROUTE-003 → `VALID_SUBSCRIPTION` ; ROUTE-001 → `BALANCE_DEBITED` |
| `1000000006` | EXPIRED | 10.000 | aucun | `CARD_EXPIRED` |
| `1000000007` | ACTIVE | 10.000 | périmé | `BALANCE_DEBITED` |
| `1258465854`, `1258465855` | ACTIVE | 10.000 | aucun | `BALANCE_DEBITED` (scénario « deux bus ») |

Lignes : `ROUTE-001`, `ROUTE-002`, `ROUTE-003` (autre ligne → `INVALID_ROUTE`).
`card_tag` : **exactement 10 chiffres, envoyé comme texte** (`"1258465854"`). Il n'y a plus de champ `currency` (montants en TND).

## Requête type

```json
{
  "transaction_id": "SCANNER-001-1788719400-0001",
  "card_tag": "1258465854",
  "device_id": "SCANNER-001",
  "vehicle_id": "BUS-001",
  "route_id": "ROUTE-001",
  "fare": 0.800,
  "occurred_at": "2026-09-30T18:30:00Z"
}
```

## Logique (ordre des règles)

1. Même scan déjà traité (`device_id` + `transaction_id` + `occurred_at`) → 409 `DUPLICATE_TRANSACTION` (aucun retraitement).
2. Carte inconnue → 404 `CARD_NOT_FOUND`.
3. Tarif (≤ 0, > 3 décimales, > 1000) → 400 `INVALID_FARE` ; ligne inconnue → 400 `INVALID_ROUTE`.
4. Carte bloquée / expirée → 200 `DECLINED` (`CARD_BLOCKED` / `CARD_EXPIRED`).
5. **Voyage déjà validé** → 200 `DECLINED / TRIP_ALREADY_VALIDATED` : « Votre voyage est déjà payé/validé. » (aucun débit).
6. Abonnement valide pour la ligne → `APPROVED / VALID_SUBSCRIPTION` (aucun débit).
7. Solde suffisant → débit → `APPROVED / BALANCE_DEBITED`.
8. Sinon → `DECLINED / INSUFFICIENT_BALANCE` (solde inchangé).

Un refus métier est un **HTTP 200** avec `status = DECLINED`. Erreurs de requête : 400, 404, 409, 422, 500 au format
`{"success": false, "error": {"code": "...", "message": "..."}}`.

## Deux protections différentes (à ne pas confondre)

| | Protège contre | Mécanisme |
|---|---|---|
| **Identité du scan** (`device_id` + `transaction_id` + `occurred_at`) | Le **renvoi de la même requête** (réseau instable, retry, rejeu d'un lot offline) | 409 `DUPLICATE_TRANSACTION`, rien n'est retraité |
| **Règle du voyage** | Un **nouveau scan** (nouveau `transaction_id`) de la même carte pour le même voyage | 200 `DECLINED / TRIP_ALREADY_VALIDATED` |

### `transaction_id` : qui le génère, et comment un même id peut revenir sans problème

- Il est **généré par le scanner** (pas par le backend) : en mode offline le scanner doit identifier le scan *avant* de parler au serveur.
- Un scan est identifié par **`(device_id, transaction_id, occurred_at)`** (contrainte `UNIQUE` en base). Conséquences :
  - deux scanners (bus, trains…) peuvent utiliser le même `transaction_id` sans conflit ;
  - un `transaction_id` **réutilisé un autre jour** (compteur remis à zéro, par exemple le `5` d'aujourd'hui et le `5` de demain) est un **nouveau scan**, traité normalement ;
  - pour **renvoyer le même scan** (retry), le scanner renvoie le **même `transaction_id` ET le même `occurred_at`** (l'heure du badge mémorisée, jamais « maintenant »).
- Filet de sécurité : si un renvoi part avec une autre heure, il n'est plus reconnu comme doublon, mais la règle du voyage ci-dessous l'empêche d'être débité (réponse `TRIP_ALREADY_VALIDATED`).
- Recommandé quand même : un UUID, ou `<device_id>-<epoch>-<compteur>`. L'horloge du scanner doit être fiable (NTP/GPS) : une horloge remise à une date fixe au redémarrage avec un compteur remis à zéro pourrait produire deux fois la même identité.

### Règle du voyage (configurable)

Un scan est refusé en `TRIP_ALREADY_VALIDATED` s'il existe déjà un scan **APPROVED** (abonnement ou solde) de la **même carte**, dans le
**même véhicule**, sur la **même ligne**, à moins de **`TRIP_WINDOW_MINUTES` minutes** (défaut : **60**, variable d'environnement).
- Deux voyageurs différents dans le même bus → acceptés tous les deux.
- Même carte dans un autre véhicule ou sur une autre ligne → nouveau voyage (correspondance), accepté.
- Un premier scan refusé (solde insuffisant…) ne bloque pas le suivant.
- Vérifié sous verrou de la carte : deux scans simultanés ne peuvent pas être débités tous les deux.

## `vehicle_id` et `route_id` : d'où viennent-ils ?

Le backend ne les calcule pas, il les reçoit. Côté scanner : `vehicle_id` est une **configuration fixe** du scanner (le véhicule où il est installé) ;
`route_id` vient du **poste du conducteur / de l'ordinateur de bord** (la ligne en service, qui change selon le service) ; `route_id` doit
exister côté backend, sinon `INVALID_ROUTE`.

## Synchronisation offline

`POST /api/v1/scanner/sync/transactions` : mêmes règles que `/payments` (même `PaymentService`), traitement dans l'ordre, un lot peut mélanger
résultats et erreurs (HTTP 200). `device_id` est indiqué une fois pour tout le lot. Compteurs : `total`, `processed` (= `approved` + `declined`,
hors doublons), `duplicates`.

## Tests

```bash
pytest                                  # SQLite en mémoire
TEST_DATABASE_URL=postgresql+psycopg://scanner:scanner@localhost:5432/scanner_mock_test pytest   # PostgreSQL + concurrence
```
La base de test est vidée avant chaque test : utilisez une base dédiée.

## Structure

`app/main.py` (assemblage) · `app/routers/` · `app/schemas/` · `app/models/` · `app/repositories/` · `app/services/payment_service.py` (toute la logique métier) ·
`app/dependencies/` · `app/core/` (config, exceptions, constantes) · `app/seed.py` · `alembic/` · `tests/`
