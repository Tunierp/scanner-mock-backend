"""Injection de dépendances : construit le PaymentService avec ses repositories."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.repositories.card_repository import CardRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.payment_service import PaymentService


def get_payment_service(db: Session = Depends(get_db)) -> PaymentService:
    return PaymentService(
        db=db,
        cards=CardRepository(db),
        subscriptions=SubscriptionRepository(db),
        routes=RouteRepository(db),
        transactions=TransactionRepository(db),
    )
