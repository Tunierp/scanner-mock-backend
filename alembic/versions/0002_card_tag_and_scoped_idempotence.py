"""card_token -> card_tag (10 chiffres) ; transaction_id unique PAR scanner ; index de recherche des voyages

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Anciennes cartes de test -> nouveaux numéros à 10 chiffres
OLD_TO_NEW = {
    "CARD-TEST-001": "1000000001",
    "CARD-TEST-002": "1000000002",
    "CARD-TEST-003": "1000000003",
    "CARD-TEST-004": "1000000004",
    "CARD-TEST-005": "1000000005",
    "CARD-TEST-006": "1000000006",
    "CARD-TEST-007": "1000000007",
}


def upgrade() -> None:
    # --- cards : renommage + format 10 caractères
    for old, new in OLD_TO_NEW.items():
        op.execute(
            sa.text("UPDATE cards SET card_token = :new WHERE card_token = :old").bindparams(new=new, old=old)
        )
    op.drop_index("ix_cards_card_token", table_name="cards")
    with op.batch_alter_table("cards") as batch:
        batch.alter_column(
            "card_token", new_column_name="card_tag", existing_type=sa.String(128), type_=sa.String(10),
            existing_nullable=False,
        )
    op.create_index("ix_cards_card_tag", "cards", ["card_tag"], unique=True)

    # --- transactions : unicité (device_id, transaction_id) au lieu de transaction_id seul
    op.drop_index("ix_transactions_transaction_id", table_name="transactions")
    with op.batch_alter_table("transactions") as batch:
        batch.create_unique_constraint("uq_transactions_device_transaction", ["device_id", "transaction_id"])
    op.create_index(
        "ix_transactions_trip_lookup", "transactions", ["card_id", "vehicle_id", "route_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_trip_lookup", table_name="transactions")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("uq_transactions_device_transaction", type_="unique")
    op.create_index("ix_transactions_transaction_id", "transactions", ["transaction_id"], unique=True)

    op.drop_index("ix_cards_card_tag", table_name="cards")
    with op.batch_alter_table("cards") as batch:
        batch.alter_column(
            "card_tag", new_column_name="card_token", existing_type=sa.String(10), type_=sa.String(128),
            existing_nullable=False,
        )
    op.create_index("ix_cards_card_token", "cards", ["card_token"], unique=True)
    for old, new in OLD_TO_NEW.items():
        op.execute(
            sa.text("UPDATE cards SET card_token = :old WHERE card_token = :new").bindparams(new=new, old=old)
        )
