from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.models.category import Category
from app.models.corridor import Corridor, CorridorLine
from app.models.subscription import Subscription, SubscriptionCorridor


class SubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def has_free_travel_subscription(self, card_id: int, on_date: date) -> bool:
        """Vrai si la carte a un abonnement actif, valide à `on_date`, d'une catégorie à gratuité totale
        (ex. Handicapé) : voyage gratuit sur n'importe quelle ligne."""
        active = EntityStatus.ACTIVE.value
        stmt = (
            select(Subscription.id)
            .join(Category, Category.id == Subscription.category_id)
            .where(
                Subscription.card_id == card_id,
                Subscription.status == active,
                Subscription.valid_from <= on_date,
                Subscription.valid_until >= on_date,
                Category.free_travel.is_(True),
                Category.status == active,
            )
            .limit(1)
        )
        return self.db.scalar(stmt) is not None

    def has_valid_subscription_for_line(self, card_id: int, line_id: int, on_date: date) -> bool:
        """Vrai si la carte a un abonnement actif, valide à `on_date`, dont une liaison (corridor) est desservie par la
        ligne `line_id` : tous les bus d'une liaison (22A, 22B...) sont couverts, et une ligne peut desservir plusieurs liaisons."""
        active = EntityStatus.ACTIVE.value
        stmt = (
            select(Subscription.id)
            .join(SubscriptionCorridor, SubscriptionCorridor.subscription_id == Subscription.id)
            .join(Corridor, Corridor.id == SubscriptionCorridor.corridor_id)
            .join(CorridorLine, CorridorLine.corridor_id == Corridor.id)
            .where(
                Subscription.card_id == card_id,
                Subscription.status == active,
                Subscription.valid_from <= on_date,
                Subscription.valid_until >= on_date,
                Corridor.status == active,
                CorridorLine.line_id == line_id,
            )
            .limit(1)
        )
        return self.db.scalar(stmt) is not None

    def add(self, subscription: Subscription) -> Subscription:
        self.db.add(subscription)
        self.db.flush()
        return subscription
