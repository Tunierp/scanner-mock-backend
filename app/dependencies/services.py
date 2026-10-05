"""Injection de dépendances : construit le PaymentService avec ses repositories."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.dependencies.database import get_db
from app.repositories.card_repository import CardRepository
from app.repositories.line_fare_repository import LineFareRepository
from app.repositories.line_repository import LineRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.payment_service import PaymentService


def get_payment_service(db: Session = Depends(get_db)) -> PaymentService:
    return PaymentService(
        db=db,
        cards=CardRepository(db),
        subscriptions=SubscriptionRepository(db),
        lines=LineRepository(db),
        fares=LineFareRepository(db),
        transactions=TransactionRepository(db),
        trip_window_minutes=get_settings().trip_window_minutes,
        tariff_timezone=get_settings().tariff_timezone,
    )
