"""Identité d'un scan = (device_id, transaction_id, occurred_at)

Un transaction_id réutilisé un autre jour (compteur du scanner remis à zéro) ne doit pas être pris pour un renvoi.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("uq_transactions_device_transaction", type_="unique")
        batch.create_unique_constraint("uq_transactions_scan", ["device_id", "transaction_id", "occurred_at"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("uq_transactions_scan", type_="unique")
        batch.create_unique_constraint("uq_transactions_device_transaction", ["device_id", "transaction_id"])
