"""Utilisateurs et cartes : historique de cartes, UNE SEULE carte active par utilisateur."""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.constants import CardStatus
from app.core.exceptions import ActiveCardAlreadyExistsError
from app.dependencies.database import SessionLocal
from app.models import Card
from app.services.card_service import CardService
from app.services.user_service import UserService


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def test_create_a_user_with_personal_information(db):
    user = UserService.from_session(db).create_user(
        "Sana", "Ben Ali", email="sana@example.tn", phone="+21620000000", national_id="01234567"
    )
    db.commit()
    assert user.id is not None and user.full_name == "Sana Ben Ali"


def test_a_user_can_have_several_cards_but_only_one_active(db):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    cards = CardService.from_session(db)
    first = cards.issue_card(user, "2000000001", balance=Decimal("5.000"))
    with pytest.raises(ActiveCardAlreadyExistsError):
        cards.issue_card(user, "2000000002")  # 2e carte active : refusée
    old = cards.issue_card(user, "2000000003", status=CardStatus.LOST)  # une carte non active reste possible
    db.commit()
    assert first.status == "ACTIVE" and old.status == "LOST"


def test_card_replacement_flow_keeps_history_and_a_single_active_card(db):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    cards = CardService.from_session(db)
    old = cards.issue_card(user, "2000000001")
    cards.set_status(old, CardStatus.REPLACED)  # 1) l'ancienne carte est remplacée
    new = cards.issue_card(user, "2000000002")  # 2) puis la nouvelle devient la carte active
    db.commit()
    db.refresh(user)
    assert sorted(c.status for c in user.cards) == ["ACTIVE", "REPLACED"]
    assert new.status == "ACTIVE"


def test_reactivating_a_card_is_refused_while_another_one_is_active(db):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    cards = CardService.from_session(db)
    cards.issue_card(user, "2000000001")
    other = cards.issue_card(user, "2000000002", status=CardStatus.INACTIVE)
    with pytest.raises(ActiveCardAlreadyExistsError):
        cards.set_status(other, CardStatus.ACTIVE)


def test_two_different_users_can_each_have_an_active_card(db):
    users, cards = UserService.from_session(db), CardService.from_session(db)
    cards.issue_card(users.create_user("A", "A"), "2000000001")
    cards.issue_card(users.create_user("B", "B"), "2000000002")
    db.commit()


def test_database_itself_refuses_two_active_cards_for_one_user(db):
    """Filet de sécurité : même en contournant le service, l'index unique partiel interdit une 2e carte active."""
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    db.add(Card(card_tag="2000000001", user_id=user.id, status="ACTIVE", balance=Decimal("0.000"), currency="TND"))
    db.flush()
    db.add(Card(card_tag="2000000002", user_id=user.id, status="ACTIVE", balance=Decimal("0.000"), currency="TND"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_database_allows_several_non_active_cards_for_one_user(db):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    for i, status in enumerate(["LOST", "REPLACED", "EXPIRED", "BLOCKED", "INACTIVE"]):
        db.add(Card(card_tag=f"200000000{i}", user_id=user.id, status=status, balance=Decimal("0.000"), currency="TND"))
    db.flush()


@pytest.mark.parametrize("tag", ["12345", "12345678901", "abcdefghij"])
def test_card_tag_must_be_10_digits(db, tag):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    with pytest.raises(ValueError):
        CardService.from_session(db).issue_card(user, tag)


def test_card_tag_must_be_unique(db):
    user = UserService.from_session(db).create_user("Sana", "Ben Ali")
    with pytest.raises(ValueError):
        CardService.from_session(db).issue_card(user, "1000000001")  # existe déjà dans les données de test
