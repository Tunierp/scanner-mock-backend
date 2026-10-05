from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user
