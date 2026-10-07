# Scanner Transport — Backend de test (MOCK)

> **« mock » = simulé / factice.** Ce backend *imite* le vrai système (paiement, cartes, abonnements, tarifs) avec des données
> fictives en base, pour que le développeur IoT teste ses appels API. Aucun vrai paiement, aucun vrai lecteur RFID/NFC.

Stack : Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, pytest, httpx (Docker en option).

## ⚠ API temporaire : réinitialiser les données de test

Pour remettre les données de test à zéro **sans accès au serveur** (au lieu de `python -m app.seed --reset`) :

```bash
curl -X POST http://localhost:8000/api/v1/test-data/reset
```
Ou dans Swagger (`/docs`) : section **« ⚠ Données de test (API TEMPORAIRE) »** → `POST /api/v1/test-data/reset` → *Try it out* → *Execute*. Aucun corps de requête.

Ce que ça fait (équivalent de `python -m app.seed --reset`) :
- **supprime toutes les transactions** (les `transaction_id` redeviennent utilisables) ;
- remet les **cartes de test** (`1000000001`…`1000000012`, `1236547895`, `1258465854`, `1258465855`) à leur solde et à leur état initiaux ;
- recrée ce qui manque des données de test. Les données ajoutées en dehors du seed (lignes, tarifs…) sont **conservées**.

Réponse :
```json
{"success": true, "data": {"message": "Données de test réinitialisées.", "deleted_transactions": 12,
  "cards": [{"card_tag": "1000000001", "status": "ACTIVE", "balance": 10.0}, "…"]}}
```
`cards` donne l'état des cartes de test après l'opération (c'est aussi le seul moyen de lire un solde par l'API).

Réglages (`.env`) :

| Variable | Défaut | Effet |
|---|---|---|
| `TEST_DATA_RESET_ENABLED` | `true` | `false` : l'endpoint n'est **pas enregistré** (absent de `/docs`, réponse 404). |
| `TEST_DATA_RESET_TOKEN` | *(vide)* | Si défini, l'appel doit envoyer `X-Reset-Token: <valeur>` (sinon 403 `RESET_FORBIDDEN`). **À définir si le serveur est joignable depuis Internet** : l'endpoint est destructif et sans autre authentification. |

L'opération est atomique (une seule transaction : en cas d'erreur, rien n'est modifié) et journalisée (adresse appelante).
Ne l'appelez pas pendant qu'un autre développeur teste : elle efface aussi ses transactions.

**Retirer l'API de réinitialisation** (quand elle ne sera plus utile) — tout est isolé :
1. supprimer `app/routers/data_reset.py`, `app/services/data_reset_service.py`, `app/schemas/data_reset.py`, `tests/test_data_reset.py` ;
2. dans `app/main.py` : l'import `data_reset` et le bloc `if settings.test_data_reset_enabled:` ;
3. dans `app/dependencies/services.py` : `get_data_reset_service` et son import ;
4. dans `app/core/config.py` : `test_data_reset_enabled` et `test_data_reset_token` ; dans `app/core/exceptions.py` : `ResetForbiddenError` ; dans `app/core/constants.py` : `RESET_FORBIDDEN` (code et message) ;
5. supprimer cette section du README. (Étape intermédiaire sans rien supprimer : `TEST_DATA_RESET_ENABLED=false`.)

## Bases de données

| Usage | Nom |
|---|---|
| Base principale | **`sts_navio_db`** |
| Base de test (pytest) | **`test_navio_db`** (vidée avant chaque test !) |

Création (PostgreSQL installé hors Docker) : `sudo -u postgres psql -f scripts/create_databases.sql`
(avec Docker, `sts_navio_db` est créée par `docker compose` et `test_navio_db` par `docker/initdb/01-create-test-db.sql`
au premier démarrage du volume ; si le volume existe déjà : `docker compose down -v`).
Renommer une base existante : `ALTER DATABASE scanner_mock RENAME TO sts_navio_db;` (aucune connexion ouverte).

## Lancement (sans Docker)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # DATABASE_URL pointe sur sts_navio_db
alembic upgrade head              # crée / met à jour les tables
python -m app.seed                # lignes, catégories, périodes, tarifs, utilisateurs, cartes, abonnements de test
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Swagger : <http://localhost:8000/docs> · Health : <http://localhost:8000/health> · Docker : `docker compose up --build`.
Remise à zéro des cartes de test et des transactions : `python -m app.seed --reset` ou, sans accès au serveur, l'API temporaire `POST /api/v1/test-data/reset` (voir plus haut).

### Mise à jour depuis la version précédente

```bash
pip install -r requirements.txt
alembic upgrade head              # migrations 0005 (utilisateurs, cartes, abonnements) puis 0006 (liaisons, catégories à type, fares)
python -m app.seed --reset
```
⚠ Les migrations `0005` et `0006` **suppriment** des données de test (cartes/abonnements/catégories/transactions selon la version de départ) et ne sont pas réversibles :
rechargez avec `python -m app.seed --reset`. `users`, `lines`, `line_fares` et `subscription_periods` sont conservées par `0006`.

## Modèle de données

```
users ──< cards ──< subscriptions >── categories  (type = SUBSCRIPTION)
                        │   └──────── subscription_periods
                        └──< subscription_corridors >── corridors ──< corridor_lines >── lines ──< line_fares
subscription_fares : (catégorie + liaison + période + date de début) → amount
```

| Table | Rôle |
|---|---|
| `users` | Utilisateur : nom, prénom, date de naissance, email, téléphone, CIN. |
| `cards` | Carte (`card_tag` 10 chiffres) d'un utilisateur, solde, **état** : `ACTIVE`, `INACTIVE`, `LOST`, `EXPIRED`, `BLOCKED`, `REPLACED`. Une seule `ACTIVE` par utilisateur. |
| `categories` | **Une seule table pour toutes les catégories**, colonne `type` (`SUBSCRIPTION`, `USER`, `BUS`…), `UNIQUE (type, code)`. `free_travel` = gratuité totale (Handicapé). |
| `subscription_periods` | Périodes : Mensuel (1 mois), Trimestriel (3), Semestriel (6), Annuel (12)… |
| `lines` | Lignes **exploitées** (22A, 22B, 15A…) : ce que le scanner envoie. Couvrent les deux sens. |
| `line_fares` | Tarif **au trajet** d'une ligne (un sens), historisé par `valid_from`. |
| `corridors` | **Liaisons vendues** dans les abonnements (ex. « Sousse - Msaken »). |
| `corridor_lines` | Many-to-Many liaison ↔ lignes : quels bus desservent la liaison. |
| `subscription_fares` | **Tarifs d'abonnement configurables** : un `amount` par (catégorie, liaison, période), historisé par `valid_from`. |
| `subscriptions` | Abonnement d'une carte : catégorie, **une** période, validité (`valid_from` → `valid_until`), `amount` payé. |
| `subscription_corridors` | Many-to-Many abonnement ↔ liaisons, avec la période et le tarif (`fare_id`) utilisés. |
| `transactions` | Journal des scans (`fare_amount` = tarif au trajet applicable, `amount` = montant débité). |

### Pourquoi une seule table `categories` avec une colonne `type` (et pas une table par entité)

Une catégorie a toujours la même forme (code, nom, statut) : une table par entité (`subscription_categories`, `user_categories`,
`bus_categories`…) dupliquerait la structure, les index, le code d'accès et les migrations à chaque nouveau besoin. Avec une seule
table, un nouveau type de catégorie = de **nouvelles lignes**, jamais une nouvelle table. Le défaut classique (une clé étrangère ne
vérifie pas le type) est supprimé par une **clé étrangère composite** `(category_id, category_type) → categories(id, type)` plus un `CHECK`
sur `subscriptions` et `subscription_fares` : la base refuse un abonnement qui pointe vers une catégorie de type `USER` ou `BUS`.
Les codes ne sont uniques que par type (le code `PASSENGER` peut exister pour `SUBSCRIPTION` et pour `USER`).
Les catégories d'utilisateurs (`type = 'USER'`) et de bus (`BUS`) sont prévues mais pas encore reliées à `users`/aux bus : la règle
métier qui les utilisera n'est pas définie.

### Liaisons (corridors) : ce que l'on vend n'est pas un numéro de bus

- **`lines`** = les bus exploités (22A, 22B, 15…). **`corridors`** = ce que le voyageur achète (« Sousse - Msaken »). Une liaison est
  **facturée une seule fois** quel que soit le nombre de lignes qui la desservent : `Sousse - Msaken` (22A **et** 22B) = **31 DT**, pas 62.
- Une ligne peut desservir **plusieurs liaisons** : un bus Sousse - Kalaa Kebira (15, 15A…) ou Sousse - Sidi Bou Ali (17, 17/18) qui passe par
  Hammam Sousse appartient aussi à la liaison « Sousse - Hammam Sousse » ; un abonnement Hammam Sousse le couvre.
- Au scan, un abonnement couvre la ligne si **une de ses liaisons est desservie par cette ligne** (via `corridor_lines`).
- La table `lines` seule ne pouvait pas exprimer ces cas ; `corridors` + `corridor_lines` les rendent explicites et se complètent sans changer la
  structure (ajout de liaisons et de rattachements). Les rattachements chargés (`app/data/subscription_catalog.py`) sont des **données de départ à compléter**.

### Prix d'un abonnement

`subscriptions.amount` = prix payé, calculé par `SubscriptionService` (fonction unique `compute_total`). Règle actuelle : **somme des tarifs des liaisons
distinctes** pour la catégorie et la période, lus dans `subscription_fares` (tarif applicable à la date de début). Exemple Passager annuel :
Sousse - Msaken 31.000 + Sousse - Hammam Sousse 30.000 = **61.000 DT / an** ; semestriel : 16.000 + 15.000 = **31.000 DT / semestre**.
Gratuité totale (Handicapé) : 0. Le prix est figé à la souscription (les lignes de `subscription_fares` ne sont jamais modifiées : un nouveau tarif =
une nouvelle ligne avec sa `valid_from`). Comme le prix est stocké et que la règle est isolée, une règle différente (forfait, remise) ne demande pas de
changer la base.

### Une période par abonnement

La période est portée par l'**abonnement**, jamais par une liaison. Un abonnement annuel ne contient que des liaisons ayant un tarif annuel ; un
abonnement semestriel, que des liaisons au tarif semestriel. Pour avoir les deux : **deux abonnements** sur la même carte. Garanti par le service (liaison
sans tarif pour la période → `SUBSCRIPTION_FARE_NOT_FOUND`) **et par la base** : `subscription_corridors` porte `period_id` et deux clés étrangères composites
`(subscription_id, period_id) → subscriptions` et `(fare_id, period_id, corridor_id) → subscription_fares` interdisent de mélanger les périodes ou d'utiliser
le tarif d'une autre liaison (vérifié par `tests/test_db_constraints.py`, PostgreSQL uniquement).

### Vocabulaire normalisé

- **`fare`** = un tarif (règle de prix configurée) : `line_fares`, `subscription_fares`, `FARE_NOT_FOUND`, `transactions.fare_amount`.
  Le mot `tariff` n'est plus utilisé.
- **`amount`** = toute valeur monétaire : `line_fares.amount`, `subscription_fares.amount`, `subscriptions.amount`, `transactions.amount`. Le mot `price` n'est plus utilisé.

### Services de gestion (pas d'API REST d'administration)

```python
from app.services.user_service import UserService
from app.services.card_service import CardService
from app.services.subscription_service import SubscriptionService

user = UserService.from_session(db).create_user("Ahmad", "Ben Ali", email="a@b.tn", national_id="01234567")
card = CardService.from_session(db).issue_card(user, "1236547895")          # refuse une 2e carte active
subs = SubscriptionService.from_session(db)
quote = subs.quote("UNIVERSITY", "ANNUAL", ["SOUSSE-SAHLOUL", "SOUSSE-AKOUDA"], date(2026, 1, 1))  # prix sans rien créer
sub = subs.create_subscription(card, "UNIVERSITY", "ANNUAL", ["SOUSSE-SAHLOUL", "SOUSSE-AKOUDA"], date(2026, 1, 1))
subs.add_corridor(sub, "SOUSSE-MONASTIR"); db.commit()
# Remplacer une carte : CardService.set_status(ancienne, CardStatus.REPLACED) puis issue_card(user, nouveau_tag)
```

### Ajouter des catégories, périodes, liaisons, lignes, tarifs (sans changer la structure)

Dans `app/data/subscription_catalog.py` / `app/data/sts_lines.py` puis `python -m app.seed`, ou en SQL :
```sql
INSERT INTO categories (type, code, name, free_travel, status) VALUES ('SUBSCRIPTION', 'RETIRED', 'Retraité', false, 'ACTIVE');
INSERT INTO categories (type, code, name, free_travel, status) VALUES ('USER', 'VIP', 'VIP', false, 'ACTIVE');   -- autre type, même table
INSERT INTO subscription_periods (code, name, months, status) VALUES ('BIMONTHLY', 'Bimestriel', 2, 'ACTIVE');
INSERT INTO corridors (code, name, departure, destination, status) VALUES ('SOUSSE-KONDAR', 'Sousse - Kondar', 'Sousse', 'Kondar', 'ACTIVE');
INSERT INTO corridor_lines (corridor_id, line_id)                       -- quelles lignes desservent la liaison
  SELECT c.id, l.id FROM corridors c, lines l WHERE c.code = 'SOUSSE-KONDAR' AND l.number IN ('30', '31');
INSERT INTO subscription_fares (category_id, category_type, corridor_id, period_id, amount, valid_from)
  SELECT cat.id, 'SUBSCRIPTION', c.id, p.id, 40.000, DATE '2026-01-01'
  FROM categories cat, corridors c, subscription_periods p
  WHERE cat.type = 'SUBSCRIPTION' AND cat.code = 'RETIRED' AND c.code = 'SOUSSE-KONDAR' AND p.code = 'BIMONTHLY';
```
⚠ Seuls les montants Sousse - Msaken (31.000 / an, 16.000 / semestre) et Sousse - Hammam Sousse (30.000 / an, 15.000 / semestre), catégorie Passager supposée,
viennent de l'énoncé : les autres tarifs d'abonnement du seed sont des **valeurs de test**.

## API du scanner

`POST /api/v1/scanner/payments` et `POST /api/v1/scanner/sync/transactions` (inchangés dans leur format) :
```json
{ "transaction_id": "SCANNER-001-1788719400-0001", "card_tag": "1258465854", "device_id": "SCANNER-001",
  "vehicle_id": "BUS-001", "line_number": "22A", "occurred_at": "2026-09-30T18:30:00Z" }
```
Le scanner n'envoie ni tarif ni devise. `card_tag` : 10 chiffres en texte. Un scan = `device_id` + `transaction_id` + `occurred_at` (renvoi = mêmes valeurs).

## Règles d'un scan (ordre d'application)

1. Même scan déjà traité → 409 `DUPLICATE_TRANSACTION`.
2. Carte inconnue → 404 `CARD_NOT_FOUND` ; ligne inconnue/inactive → 400 `INVALID_LINE`.
3. Carte non active → 200 `DECLINED` : `CARD_BLOCKED`, `CARD_EXPIRED`, `CARD_LOST` (perdue), `CARD_REPLACED` (remplacée), `CARD_NOT_ACTIVE` (non active).
4. Voyage déjà validé (même carte + véhicule + ligne, scan accepté dans les `TRIP_WINDOW_MINUTES`, défaut 60) → `DECLINED / TRIP_ALREADY_VALIDATED`.
5. **Abonnement d'une catégorie gratuite (Handicapé), valide → `APPROVED / FREE_TRAVEL_CATEGORY` : n'importe quelle ligne, aucun débit.**
6. Abonnement valide (statut actif, date du scan entre `valid_from` et `valid_until`, heure locale `BUSINESS_TIMEZONE`) **dont une liaison est desservie par la ligne** →
   `APPROVED / VALID_SUBSCRIPTION`, aucun débit, même si la ligne n'a pas de tarif au trajet. Une carte avec plusieurs abonnements est couverte par l'ensemble de leurs liaisons.
7. Aucun tarif au trajet pour la ligne à cette date → 404 `FARE_NOT_FOUND`.
8. Solde ≥ tarif → débit → `BALANCE_DEBITED` ; sinon `DECLINED / INSUFFICIENT_BALANCE`.

Nouveaux codes : `FREE_TRAVEL_CATEGORY`, `CARD_NOT_ACTIVE`, `CARD_LOST`, `CARD_REPLACED` (scan) ; `ACTIVE_CARD_ALREADY_EXISTS`, `CATEGORY_NOT_FOUND`,
`PERIOD_NOT_FOUND`, `CORRIDOR_NOT_FOUND`, `SUBSCRIPTION_FARE_NOT_FOUND` (services de gestion).

## Cartes de test (tarif au trajet courant de la 22A : 1.200)

| `card_tag` | Utilisateur / état | Solde | Abonnement(s) | Résultat |
|---|---|---|---|---|
| `1000000001` | ACTIVE | 10.000 | Passager annuel : liaisons Msaken, Monastir, Jammel (86.000) | lignes 22A, **22B**, 52A/B/C, 61 : gratuit · ligne 28 : `FARE_NOT_FOUND` |
| `1000000002` | ACTIVE | 0.300 | – | 22A : `INSUFFICIENT_BALANCE` |
| `1000000003` | ACTIVE | 10.000 | – | 22A : `BALANCE_DEBITED` (→ 8.800) |
| `1000000004` | BLOCKED | 10.000 | – | `CARD_BLOCKED` |
| `1000000005` | ACTIVE | 10.000 | Passager annuel : liaison Jammel (ligne 61) | 61 : gratuit · 22A : `BALANCE_DEBITED` |
| `1000000006` | EXPIRED | 10.000 | – | `CARD_EXPIRED` |
| `1000000007` | ACTIVE | 10.000 | Passager annuel 2025 (périmé) : liaison Msaken | 22A : `BALANCE_DEBITED` |
| `1000000008` | ACTIVE | 10.000 | **Handicapé** annuel (aucune ligne) | **toutes les lignes : `FREE_TRAVEL_CATEGORY`** |
| `1000000009` / `1000000010` / `1000000011` | LOST / REPLACED / ACTIVE (même utilisatrice, Rim) | 10.000 | – | `CARD_LOST` / `CARD_REPLACED` / `BALANCE_DEBITED` |
| `1000000012` | INACTIVE | 10.000 | – | `CARD_NOT_ACTIVE` |
| `1236547895` | Ahmad, ACTIVE | 10.000 | ① Universitaire annuel : Sousse-Sahloul + Sousse-Akouda (42.000) ② Passager annuel : Sousse-Monastir (30.000) | 13C, 16, 52A… : gratuit · 22A : `BALANCE_DEBITED` |
| `1258465854`, `1258465855` | ACTIVE | 10.000 | – | 22A : `BALANCE_DEBITED` (scénario « deux bus ») |

## Identité d'un scan et voyage déjà validé

`transaction_id` est généré par le scanner ; un scan = `device_id` + `transaction_id` + `occurred_at` (contrainte `UNIQUE`). Même id un autre jour ou sur
un autre scanner = nouveau scan. Un nouveau scan de la même carte pour le même voyage est refusé (`TRIP_ALREADY_VALIDATED`), y compris pour la catégorie
gratuite. Une ligne couvrant les deux sens et le scanner n'envoyant pas de sens, un aller puis un retour sur le même véhicule dans la fenêtre sont
considérés comme le même voyage. Débit et enregistrement dans une seule transaction PostgreSQL, carte verrouillée (`SELECT … FOR UPDATE`).

## Tests

```bash
pytest                                  # SQLite en mémoire
TEST_DATABASE_URL=postgresql+psycopg://scanner:scanner@localhost:5432/test_navio_db pytest   # PostgreSQL + concurrence
```
⚠ La base ciblée est **vidée** avant chaque test : n'utilisez jamais `sts_navio_db` comme `TEST_DATABASE_URL`.

## Structure

`app/main.py` · `app/routers/` · `app/schemas/` · `app/models/` (User, Card, Category, Line, LineFare, Corridor, CorridorLine, Subscription, SubscriptionCorridor,
SubscriptionPeriod, SubscriptionFare, Transaction) · `app/repositories/` · `app/services/` (`payment_service` = scan ; `user_service`, `card_service`,
`subscription_service` = gestion) · `app/dependencies/` · `app/core/` · `app/data/` (lignes, catégories, périodes, tarifs) · `app/seed.py` ·
`alembic/` · `scripts/create_databases.sql` · `docker/initdb/` · `tests/`
