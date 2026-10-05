"""Création d'utilisateurs (services de gestion : appelés par le seed, les tests ou une future API d'administration)."""
from datetime import date

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, db: Session, users: UserRepository):
        self.db = db
        self.users = users

    @classmethod
    def from_session(cls, db: Session) -> "UserService":
        return cls(db, UserRepository(db))

    def create_user(
        self,
        first_name: str,
        last_name: str,
        *,
        birth_date: date | None = None,
        email: str | None = None,
        phone: str | None = None,
        national_id: str | None = None,
    ) -> User:
        """Crée un utilisateur (flush, sans commit : c'est l'appelant qui valide la transaction)."""
        user = User(
            first_name=first_name, last_name=last_name, birth_date=birth_date,
            email=email, phone=phone, national_id=national_id,
        )
        return self.users.add(user)
