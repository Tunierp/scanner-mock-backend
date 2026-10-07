"""Catégories à type unique, liaisons (corridors), tarifs d'abonnement par liaison, règle « une période par abonnement »

- `categories` : une seule table pour toutes les entités (colonne `type` : SUBSCRIPTION, USER, BUS...) ;
- `corridors` + `corridor_lines` : les liaisons VENDUES (ex. « Sousse - Msaken ») regroupent plusieurs lignes (22A, 22B...) ;
- `subscription_tariffs` devient `subscription_fares` (terme unique : fare) et porte sur une liaison ;
- `subscription_lines` devient `subscription_corridors` ; `subscriptions.amount` = prix payé ;
- clés étrangères composites : catégorie du bon type, période de la liaison = période de l'abonnement, tarif de la bonne
  liaison et de la bonne période ;
- `transactions.fare` devient `transactions.fare_amount`.
Les données de TEST concernées (abonnements, catégories, transactions) sont supprimées : les recharger avec
`python -m app.seed`. `users`, `cards`, `lines`, `line_fares` et `subscription_periods` sont conservées.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("subscription_lines")
    op.drop_table("subscriptions")
    op.drop_table("subscription_tariffs")
    op.drop_table("categories")

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("free_travel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("type", "code", name="uq_categories_type_code"),
        sa.UniqueConstraint("id", "type", name="uq_categories_id_type"),
    )

    op.create_table(
        "corridors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("departure", sa.String(100), nullable=False),
        sa.Column("destination", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("ix_corridors_code", "corridors", ["code"], unique=True)

    op.create_table(
        "corridor_lines",
        sa.Column("corridor_id", sa.Integer(), sa.ForeignKey("corridors.id"), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), primary_key=True),
    )

    op.create_table(
        "subscription_fares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("category_type", sa.String(20), nullable=False, server_default="SUBSCRIPTION"),
        sa.Column("corridor_id", sa.Integer(), sa.ForeignKey("corridors.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("subscription_periods.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id", "category_type"], ["categories.id", "categories.type"], name="fk_subscription_fares_category"
        ),
        sa.CheckConstraint("category_type = 'SUBSCRIPTION'", name="ck_subscription_fares_category_type"),
        sa.UniqueConstraint("category_id", "corridor_id", "period_id", "valid_from", name="uq_subscription_fares_rule"),
        sa.UniqueConstraint("id", "period_id", "corridor_id", name="uq_subscription_fares_id_period_corridor"),
        sa.CheckConstraint("amount >= 0", name="ck_subscription_fares_amount_non_negative"),
    )
    op.create_index("ix_subscription_fares_corridor_id", "subscription_fares", ["corridor_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("category_type", sa.String(20), nullable=False, server_default="SUBSCRIPTION"),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("subscription_periods.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id", "category_type"], ["categories.id", "categories.type"], name="fk_subscriptions_category"
        ),
        sa.CheckConstraint("category_type = 'SUBSCRIPTION'", name="ck_subscriptions_category_type"),
        sa.CheckConstraint("valid_until >= valid_from", name="ck_subscriptions_dates"),
        sa.CheckConstraint("amount >= 0", name="ck_subscriptions_amount_non_negative"),
        sa.UniqueConstraint("id", "period_id", name="uq_subscriptions_id_period"),
    )
    op.create_index("ix_subscriptions_card_id", "subscriptions", ["card_id"])

    op.create_table(
        "subscription_corridors",
        sa.Column("subscription_id", sa.Integer(), primary_key=True),
        sa.Column("corridor_id", sa.Integer(), sa.ForeignKey("corridors.id"), primary_key=True),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("fare_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id", "period_id"], ["subscriptions.id", "subscriptions.period_id"],
            name="fk_subscription_corridors_subscription_period",
        ),
        sa.ForeignKeyConstraint(
            ["fare_id", "period_id", "corridor_id"],
            ["subscription_fares.id", "subscription_fares.period_id", "subscription_fares.corridor_id"],
            name="fk_subscription_corridors_fare",
        ),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.String(64), nullable=False),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), nullable=False),
        sa.Column("fare_amount", sa.Numeric(12, 3), nullable=True),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("balance_before", sa.Numeric(12, 3), nullable=True),
        sa.Column("balance_after", sa.Numeric(12, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("device_id", "transaction_id", "occurred_at", name="uq_transactions_scan"),
    )
    op.create_index("ix_transactions_card_id", "transactions", ["card_id"])
    op.create_index(
        "ix_transactions_trip_lookup", "transactions", ["card_id", "vehicle_id", "line_id", "occurred_at"]
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Migration irréversible (abonnements, catégories et transactions de test supprimés). "
        "Recréez la base avec `alembic upgrade head` puis `python -m app.seed`."
    )
