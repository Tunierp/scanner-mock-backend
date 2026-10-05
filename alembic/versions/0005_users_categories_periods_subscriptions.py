"""Utilisateurs, catégories, périodes, tarifs d'abonnement ; abonnements liés aux cartes et aux lignes

- crée `users`, `categories`, `subscription_periods`, `subscription_tariffs` ;
- refond `cards` (+ `user_id` obligatoire, une seule carte ACTIVE par utilisateur), `subscriptions` (carte, catégorie,
  période, dates de validité) et `subscription_lines` (Many-to-Many avec prix figé) ;
- supprime `card_subscriptions` (fusionnée dans `subscriptions`) ;
- CONSERVE `lines` et `line_fares`.
Les anciennes données de TEST (cartes, abonnements, transactions) sont supprimées : les recharger avec
`python -m app.seed`.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- anciennes tables de test (ordre : dépendants d'abord)
    op.drop_table("transactions")
    op.drop_table("card_subscriptions")
    op.drop_table("subscription_lines")
    op.drop_table("subscriptions")
    op.drop_table("cards")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("national_id", sa.String(30), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("free_travel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("ix_categories_code", "categories", ["code"], unique=True)

    op.create_table(
        "subscription_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.CheckConstraint("months > 0", name="ck_subscription_periods_months_positive"),
    )
    op.create_index("ix_subscription_periods_code", "subscription_periods", ["code"], unique=True)

    op.create_table(
        "subscription_tariffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("subscription_periods.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.UniqueConstraint("category_id", "line_id", "period_id", "valid_from", name="uq_subscription_tariffs_rule"),
        sa.CheckConstraint("amount >= 0", name="ck_subscription_tariffs_amount_non_negative"),
    )
    op.create_index("ix_subscription_tariffs_line_id", "subscription_tariffs", ["line_id"])

    op.create_table(
        "cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_tag", sa.String(10), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("balance", sa.Numeric(12, 3), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_cards_balance_non_negative"),
    )
    op.create_index("ix_cards_card_tag", "cards", ["card_tag"], unique=True)
    op.create_index("ix_cards_user_id", "cards", ["user_id"])
    # Un utilisateur ne peut avoir qu'UNE SEULE carte active (index unique partiel).
    op.create_index(
        "uq_cards_one_active_per_user", "cards", ["user_id"], unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"), sqlite_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("subscription_periods.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("valid_until >= valid_from", name="ck_subscriptions_dates"),
    )
    op.create_index("ix_subscriptions_card_id", "subscriptions", ["card_id"])

    op.create_table(
        "subscription_lines",
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), primary_key=True),
        sa.Column("price", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("price >= 0", name="ck_subscription_lines_price_non_negative"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.String(64), nullable=False),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), nullable=False),
        sa.Column("fare", sa.Numeric(12, 3), nullable=True),
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
        "Migration irréversible (cartes, abonnements et transactions de test supprimés). "
        "Recréez la base de test avec `alembic upgrade head` puis `python -m app.seed`."
    )
