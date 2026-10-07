"""Abonnements : calcul du prix à partir des tarifs configurés en base, création, ajout de liaisons.

Ce que l'on VEND, ce sont des LIAISONS (corridors, ex. « Sousse - Msaken »), pas des numéros de bus : une liaison est
facturée UNE fois, même si plusieurs lignes la desservent (22A et 22B : 31 DT, pas 62 DT). Un abonnement couvre
toutes les lignes de ses liaisons (table `corridor_lines`).

Prix : la règle actuelle est « somme des tarifs des liaisons distinctes » pour la catégorie et la période de l'abonnement
(table `subscription_fares`, tarif applicable à la date de début). Elle est isolée dans `compute_total` : changer la règle
(remise, forfait...) ne touche ni la structure de la base ni les scans. Catégorie à gratuité totale (ex. Handicapé) : 0.
Un abonnement n'a qu'UNE période : annuel = liaisons au tarif annuel, semestriel = liaisons au tarif semestriel
(un corridor sans tarif pour la période de l'abonnement est refusé). Pour mélanger : deux abonnements sur la même carte.
Aucun montant n'est codé en dur : tout vient de la base.
"""
import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import CategoryType, EntityStatus
from app.core.exceptions import (
    CategoryNotFoundError,
    CorridorNotFoundError,
    PeriodNotFoundError,
    SubscriptionFareNotFoundError,
)
from app.models.card import Card
from app.models.category import Category
from app.models.corridor import Corridor
from app.models.subscription import Subscription, SubscriptionCorridor, SubscriptionPeriod
from app.repositories.category_repository import CategoryRepository
from app.repositories.corridor_repository import CorridorRepository
from app.repositories.period_repository import PeriodRepository
from app.repositories.subscription_fare_repository import SubscriptionFareRepository
from app.repositories.subscription_repository import SubscriptionRepository

ZERO = Decimal("0.000")


def add_months(day: date, months: int) -> date:
    """`day` + `months` mois (le jour est ramené à la fin du mois si besoin : 31 janvier + 1 mois = 28/29 février)."""
    year_shift, month_index = divmod(day.month - 1 + months, 12)
    year, month = day.year + year_shift, month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def end_of_period(start: date, months: int) -> date:
    """Dernier jour (inclus) d'un abonnement qui commence le `start` : 1er janvier + 12 mois -> 31 décembre."""
    return add_months(start, months) - timedelta(days=1)


def compute_total(amounts: Iterable[Decimal]) -> Decimal:
    """RÈGLE DE PRIX de l'abonnement : somme des tarifs des liaisons. Point unique à modifier si la règle évolue."""
    return sum(amounts, ZERO).quantize(Decimal("0.001"))


@dataclass(frozen=True)
class QuoteCorridor:
    corridor: Corridor
    fare_id: int | None  # None : catégorie à gratuité totale (aucun tarif)
    amount: Decimal


@dataclass(frozen=True)
class Quote:
    category: Category
    period: SubscriptionPeriod
    corridors: list[QuoteCorridor]
    total: Decimal


class SubscriptionService:
    def __init__(
        self,
        db: Session,
        categories: CategoryRepository,
        periods: PeriodRepository,
        corridors: CorridorRepository,
        fares: SubscriptionFareRepository,
        subscriptions: SubscriptionRepository,
    ):
        self.db = db
        self.categories = categories
        self.periods = periods
        self.corridors = corridors
        self.fares = fares
        self.subscriptions = subscriptions

    @classmethod
    def from_session(cls, db: Session) -> "SubscriptionService":
        return cls(
            db, CategoryRepository(db), PeriodRepository(db), CorridorRepository(db),
            SubscriptionFareRepository(db), SubscriptionRepository(db),
        )

    # ------------------------------------------------------------------ prix

    def quote(self, category_code: str, period_code: str, corridor_codes: list[str], on_date: date) -> Quote:
        """Calcule le prix (sans rien créer) : tarif de chaque liaison pour cette catégorie et cette période."""
        category = self.categories.get_active_by_code(category_code, CategoryType.SUBSCRIPTION)
        if category is None:
            raise CategoryNotFoundError(f"Catégorie d'abonnement inconnue ou inactive : {category_code}.")
        period = self.periods.get_active_by_code(period_code)
        if period is None:
            raise PeriodNotFoundError(f"Période inconnue ou inactive : {period_code}.")

        quoted: list[QuoteCorridor] = []
        for code in dict.fromkeys(corridor_codes):  # doublons ignorés, ordre conservé
            corridor = self.corridors.get_active_by_code(code)
            if corridor is None:
                raise CorridorNotFoundError(f"Liaison inconnue ou inactive : {code}.")
            quoted.append(self._quote_corridor(category, period, corridor, on_date))
        return Quote(category, period, quoted, compute_total(q.amount for q in quoted))

    def _quote_corridor(
        self, category: Category, period: SubscriptionPeriod, corridor: Corridor, on_date: date
    ) -> QuoteCorridor:
        if category.free_travel:
            return QuoteCorridor(corridor, None, ZERO)
        fare = self.fares.get_applicable(category.id, corridor.id, period.id, on_date)
        if fare is None:
            raise SubscriptionFareNotFoundError(
                f"Aucun tarif d'abonnement pour la liaison {corridor.code}, la catégorie {category.code} "
                f"et la période {period.code} au {on_date.isoformat()} "
                f"(un abonnement {period.code} ne peut contenir que des liaisons ayant un tarif {period.code})."
            )
        return QuoteCorridor(corridor, fare.id, Decimal(fare.amount).quantize(Decimal("0.001")))

    # ------------------------------------------------------------------ création

    def create_subscription(
        self, card: Card, category_code: str, period_code: str, corridor_codes: list[str], start_date: date
    ) -> Subscription:
        """Crée un abonnement pour la carte (flush, sans commit).

        La durée vient de la période (ex. annuel : du 01/01/2026 au 31/12/2026). Chaque liaison garde la référence du
        tarif utilisé (`fare_id`) et l'abonnement le prix payé (`amount`) : un changement de tarif ultérieur ne modifie
        pas les abonnements existants. Une catégorie à gratuité totale peut n'avoir aucune liaison ; sinon au moins une.
        """
        quote = self.quote(category_code, period_code, corridor_codes, start_date)
        if not quote.corridors and not quote.category.free_travel:
            raise CorridorNotFoundError("Un abonnement doit contenir au moins une liaison.")
        subscription = Subscription(
            card_id=card.id,
            category_id=quote.category.id,
            category_type=CategoryType.SUBSCRIPTION.value,
            period_id=quote.period.id,
            valid_from=start_date,
            valid_until=end_of_period(start_date, quote.period.months),
            amount=quote.total,
            status=EntityStatus.ACTIVE.value,
        )
        subscription.subscription_corridors = [
            SubscriptionCorridor(corridor_id=qc.corridor.id, period_id=quote.period.id, fare_id=qc.fare_id)
            for qc in quote.corridors
        ]
        return self.subscriptions.add(subscription)

    def add_corridor(self, subscription: Subscription, corridor_code: str) -> Subscription:
        """Ajoute une liaison à un abonnement existant, avec la période de l'abonnement et le tarif applicable à sa date
        de début, puis met le prix à jour. Sans effet si la liaison est déjà présente."""
        if any(sc.corridor.code == corridor_code for sc in subscription.subscription_corridors):
            return subscription
        corridor = self.corridors.get_active_by_code(corridor_code)
        if corridor is None:
            raise CorridorNotFoundError(f"Liaison inconnue ou inactive : {corridor_code}.")
        qc = self._quote_corridor(subscription.category, subscription.period, corridor, subscription.valid_from)
        subscription.subscription_corridors.append(
            SubscriptionCorridor(corridor_id=corridor.id, period_id=subscription.period_id, fare_id=qc.fare_id)
        )
        subscription.amount = compute_total([subscription.amount, qc.amount])
        self.db.flush()
        return subscription
