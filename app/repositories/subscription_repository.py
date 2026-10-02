from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.models.route import Route
from app.models.subscription import CardSubscription, Subscription, SubscriptionRoute


class SubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def has_valid_subscription_for_route(self, card_id: int, route_code: str, at: datetime) -> bool:
        """Vrai si la carte a un abonnement actif, valide à `at`, couvrant la ligne `route_code`."""
        active = EntityStatus.ACTIVE.value
        stmt = (
            select(CardSubscription.id)
            .join(Subscription, Subscription.id == CardSubscription.subscription_id)
            .join(SubscriptionRoute, SubscriptionRoute.subscription_id == Subscription.id)
            .join(Route, Route.id == SubscriptionRoute.route_id)
            .where(
                CardSubscription.card_id == card_id,
                CardSubscription.status == active,
                Subscription.status == active,
                CardSubscription.valid_from <= at,
                CardSubscription.valid_until >= at,
                Route.code == route_code,
                Route.status == active,
            )
            .limit(1)
        )
        return self.db.scalar(stmt) is not None
