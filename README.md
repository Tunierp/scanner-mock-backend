# Scanner Transport — Backend de test (MOCK)

> **« mock » = simulé / factice.** Ce backend *imite* le vrai système (paiement, cartes, abonnements, tarifs) avec des données
> fictives en base, pour que le développeur IoT teste ses appels API. Aucun vrai paiement, aucun vrai lecteur RFID/NFC.

Stack : Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, pytest, httpx (Docker en option).

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
Remise à zéro des cartes de test et des transactions : `python -m app.seed --reset`.

### Mise à jour depuis la version précédente

```bash
pip install -r requirements.txt
alembic upgrade head              # migration 0005 : utilisateurs, catégories, périodes, tarifs, abonnements refondus
python -m app.seed --reset
```
⚠ La migration `0005` **supprime** les tables de test `cards`, `card_subscriptions`, `subscriptions`, `subscription_lines`
et `transactions` (à recharger avec le seed) et n'est pas réversible. `lines` et `line_fares` sont conservées.

## Modèle de données

```
users ──< cards ──< subscriptions >── categories
                        │   └──────── subscription_periods
                        └──< subscription_lines >── lines ──< line_fares
subscription_tariffs : (catégorie + ligne + période + date de début) → montant
```

| Table | Rôle |
|---|---|
| `users` | Utilisateur : nom, prénom, date de naissance, email, téléphone, CIN. |
| `cards` | Carte (`card_tag` 10 chiffres) **appartenant à un utilisateur**, solde, **état** : `ACTIVE`, `INACTIVE`, `LOST`, `EXPIRED`, `BLOCKED`, `REPLACED`. |
| `categories` | Catégories d'abonnés : Universitaire, Scolaire, Handicapé, Passager, Travailleur, Stagiaire… `free_travel` = gratuité sur **toutes** les lignes (vrai pour Handicapé). |
| `subscription_periods` | Périodes : Mensuel (1 mois), Trimestriel (3), Semestriel (6), Annuel (12)… |
| `subscriptions` | Abonnement **d'une carte**, avec une **catégorie**, une **période**, une validité (`valid_from` → `valid_until`, dates incluses). |
| `subscription_lines` | Many-to-Many abonnement ↔ lignes, avec le **prix de la ligne figé** à la souscription. |
| `subscription_tariffs` | **Tarifs d'abonnement configurables** : un montant par (catégorie, ligne, période), historisé par `valid_from`. |
| `lines`, `line_fares` | Lignes (numéro, départ, destination, `via`) couvrant les deux sens, et tarifs **au trajet** (un sens) historisés. |
| `transactions` | Journal des scans. |

**Règles garanties par la base** : un utilisateur ne peut avoir **qu'une seule carte `ACTIVE`** (index unique partiel
`uq_cards_one_active_per_user`) mais autant de cartes non actives qu'il veut (historique) ; une carte peut avoir **plusieurs abonnements** ;
un abonnement peut contenir **plusieurs lignes** et une ligne peut être dans **plusieurs abonnements** ; un tarif d'abonnement est unique par
(catégorie, ligne, période, date de début).

**Prix d'un abonnement** = somme des tarifs de ses lignes pour sa catégorie et sa période (tarif applicable à la date de début, lu dans
`subscription_tariffs`). Exemple (Passager, annuel) : Sousse→Msaken 31.000 + Sousse→Hammam Sousse 30.000 = **61.000 DT / an** ; en semestriel :
16.000 + 15.000 = **31.000 DT / semestre**. Catégorie à gratuité totale (Handicapé) : toutes les lignes à 0, prix total 0. Le prix de chaque ligne
est **figé** dans l'abonnement : changer un tarif plus tard ne modifie pas les abonnements existants.

### Services de gestion (pas d'API REST d'administration)

Ces opérations sont des services Python, utilisés par le seed et les tests (une API d'administration pourra s'appuyer dessus) :

```python
from app.services.user_service import UserService
from app.services.card_service import CardService
from app.services.subscription_service import SubscriptionService

user = UserService.from_session(db).create_user("Ahmad", "Ben Ali", email="a@b.tn", national_id="01234567")
card = CardService.from_session(db).issue_card(user, "1236547895")          # refuse une 2e carte active
subs = SubscriptionService.from_session(db)
quote = subs.quote("UNIVERSITY", "ANNUAL", ["13C", "16"], date(2026, 1, 1))  # prix sans rien créer
sub = subs.create_subscription(card, "UNIVERSITY", "ANNUAL", ["13C", "16"], date(2026, 1, 1))
subs.add_line(sub, "52A"); db.commit()
# Remplacer une carte : CardService.set_status(ancienne, CardStatus.REPLACED) puis issue_card(user, nouveau_tag)
```

### Ajouter des catégories, périodes, lignes, tarifs (sans changer la structure)

Dans `app/data/subscription_catalog.py` / `app/data/sts_lines.py` puis `python -m app.seed`, ou en SQL :
```sql
INSERT INTO categories (code, name, free_travel, status) VALUES ('RETIRED', 'Retraité', false, 'ACTIVE');
INSERT INTO subscription_periods (code, name, months, status) VALUES ('BIMONTHLY', 'Bimestriel', 2, 'ACTIVE');
INSERT INTO lines (number, departure, destination, status) VALUES ('30', 'Sousse', 'Kondar', 'ACTIVE');
INSERT INTO subscription_tariffs (category_id, line_id, period_id, amount, valid_from)
  SELECT c.id, l.id, p.id, 40.000, DATE '2026-01-01'
  FROM categories c, lines l, subscription_periods p WHERE c.code='RETIRED' AND l.number='30' AND p.code='BIMONTHLY';
```
⚠ Seuls les montants de la ligne 22A (31.000 / an, 16.000 / semestre, Passager) viennent de l'énoncé : les autres tarifs d'abonnement du seed sont des **valeurs de test**.

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
6. Abonnement valide (statut actif, date du scan entre `valid_from` et `valid_until`, heure locale `TARIFF_TIMEZONE`) **contenant la ligne** →
   `APPROVED / VALID_SUBSCRIPTION`, aucun débit, même si la ligne n'a pas de tarif. Une carte avec plusieurs abonnements est couverte par l'ensemble de leurs lignes.
7. Aucun tarif au trajet pour la ligne à cette date → 404 `FARE_NOT_FOUND`.
8. Solde ≥ tarif → débit → `BALANCE_DEBITED` ; sinon `DECLINED / INSUFFICIENT_BALANCE`.

Nouveaux codes : `FREE_TRAVEL_CATEGORY`, `CARD_NOT_ACTIVE`, `CARD_LOST`, `CARD_REPLACED` (scan) ; `ACTIVE_CARD_ALREADY_EXISTS`, `CATEGORY_NOT_FOUND`,
`PERIOD_NOT_FOUND`, `SUBSCRIPTION_TARIFF_NOT_FOUND` (services de gestion).

## Cartes de test (tarif au trajet courant de la 22A : 1.200)

| `card_tag` | Utilisateur / état | Solde | Abonnement(s) | Résultat |
|---|---|---|---|---|
| `1000000001` | ACTIVE | 10.000 | Passager annuel : 22A, 52A, 61 (86.000) | ces lignes : gratuit · ligne 28 : `FARE_NOT_FOUND` |
| `1000000002` | ACTIVE | 0.300 | – | 22A : `INSUFFICIENT_BALANCE` |
| `1000000003` | ACTIVE | 10.000 | – | 22A : `BALANCE_DEBITED` (→ 8.800) |
| `1000000004` | BLOCKED | 10.000 | – | `CARD_BLOCKED` |
| `1000000005` | ACTIVE | 10.000 | Passager annuel : 61 | 61 : gratuit · 22A : `BALANCE_DEBITED` |
| `1000000006` | EXPIRED | 10.000 | – | `CARD_EXPIRED` |
| `1000000007` | ACTIVE | 10.000 | Passager annuel 2025 (périmé) : 22A | 22A : `BALANCE_DEBITED` |
| `1000000008` | ACTIVE | 10.000 | **Handicapé** annuel (aucune ligne) | **toutes les lignes : `FREE_TRAVEL_CATEGORY`** |
| `1000000009` / `1000000010` / `1000000011` | LOST / REPLACED / ACTIVE (même utilisatrice, Rim) | 10.000 | – | `CARD_LOST` / `CARD_REPLACED` / `BALANCE_DEBITED` |
| `1000000012` | INACTIVE | 10.000 | – | `CARD_NOT_ACTIVE` |
| `1236547895` | Ahmad, ACTIVE | 10.000 | ① Universitaire annuel : 13C, 16 (42.000) ② Passager annuel : 52A (30.000) | 13C, 16, 52A : gratuit · 22A : `BALANCE_DEBITED` |
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

`app/main.py` · `app/routers/` · `app/schemas/` · `app/models/` (User, Card, Category, Line, LineFare, Subscription, SubscriptionLine, SubscriptionPeriod,
SubscriptionTariff, Transaction) · `app/repositories/` · `app/services/` (`payment_service` = scan ; `user_service`, `card_service`,
`subscription_service` = gestion) · `app/dependencies/` · `app/core/` · `app/data/` (lignes, catégories, périodes, tarifs) · `app/seed.py` ·
`alembic/` · `scripts/create_databases.sql` · `docker/initdb/` · `tests/`
