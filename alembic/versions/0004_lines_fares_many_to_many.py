"""Route -> Ligne, abonnements Many-to-Many avec les lignes, tarifs historisés par ligne

- supprime `routes`, `subscription_routes` et `transactions` (données de TEST : à recharger avec
  `python -m app.seed`) ; conserve `cards`, `subscriptions` et `card_subscriptions` ;
- crée `lines`, `line_fares`, `subscription_lines` et recrée `transactions` (référence `line_id`,
  `fare` devient nullable : une ligne peut ne pas avoir de tarif).

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("subscription_routes")
    op.drop_table("routes")

    op.create_table(
        "lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(16), nullable=False),
        sa.Column("departure", sa.String(100), nullable=False),
        sa.Column("destination", sa.String(100), nullable=False),
        sa.Column("via", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("ix_lines_number", "lines", ["number"], unique=True)

    op.create_table(
        "line_fares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.UniqueConstraint("line_id", "valid_from", name="uq_line_fares_line_valid_from"),
        sa.CheckConstraint("amount > 0", name="ck_line_fares_amount_positive"),
    )
    op.create_index("ix_line_fares_line_id", "line_fares", ["line_id"])

    op.create_table(
        "subscription_lines",
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), primary_key=True),
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
        "Migration irréversible (les tables routes/transactions de test sont supprimées). "
        "Recréez la base de test avec `alembic upgrade head` puis `python -m app.seed`."
    )
