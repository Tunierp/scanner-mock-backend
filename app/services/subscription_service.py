"""Abonnements : calcul du prix à partir des tarifs configurés en base, création, ajout de lignes.

Prix d'un abonnement = SOMME des tarifs de ses lignes, pour la catégorie et la période choisies
(table `subscription_tariffs`, applicable à la date de début de l'abonnement).
Catégorie à gratuité totale (ex. Handicapé) : toutes les lignes sont à 0, le prix total est 0.
Aucun montant n'est codé en dur : tout vient de la base.
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import EntityStatus
from app.core.exceptions import (
    CategoryNotFoundError,
    InvalidLineError,
    PeriodNotFoundError,
    SubscriptionTariffNotFoundError,
)
from app.models.card import Card
from app.models.category import Category
from app.models.line import Line
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionPeriod
from app.repositories.category_repository import CategoryRepository
from app.repositories.line_repository import LineRepository
from app.repositories.period_repository import PeriodRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.subscription_tariff_repository import SubscriptionTariffRepository

ZERO = Decimal("0.000")


def add_months(day: date, months: int) -> date:
    """`day` + `months` mois (le jour est ramené à la fin du mois si besoin : 31 janvier + 1 mois = 28/29 février)."""
    year_shift, month_index = divmod(day.month - 1 + months, 12)
    year, month = day.year + year_shift, month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def end_of_period(start: date, months: int) -> date:
    """Dernier jour (inclus) d'un abonnement qui commence le `start` : 1er janvier + 12 mois -> 31 décembre."""
    return add_months(start, months) - timedelta(days=1)


@dataclass(frozen=True)
class QuoteLine:
    line: Line
    price: Decimal


@dataclass(frozen=True)
class Quote:
    category: Category
    period: SubscriptionPeriod
    lines: list[QuoteLine]
    total: Decimal


class SubscriptionService:
    def __init__(
        self,
        db: Session,
        categories: CategoryRepository,
        periods: PeriodRepository,
        lines: LineRepository,
        tariffs: SubscriptionTariffRepository,
        subscriptions: SubscriptionRepository,
    ):
        self.db = db
        self.categories = categories
        self.periods = periods
        self.lines = lines
        self.tariffs = tariffs
        self.subscriptions = subscriptions

    @classmethod
    def from_session(cls, db: Session) -> "SubscriptionService":
        return cls(
            db, CategoryRepository(db), PeriodRepository(db), LineRepository(db),
            SubscriptionTariffRepository(db), SubscriptionRepository(db),
        )

    # ------------------------------------------------------------------ prix

    def quote(self, category_code: str, period_code: str, line_numbers: list[str], on_date: date) -> Quote:
        """Calcule le prix (sans rien créer) : tarif de chaque ligne pour cette catégorie et cette période."""
        category = self.categories.get_active_by_code(category_code)
        if category is None:
            raise CategoryNotFoundError(f"Catégorie inconnue ou inactive : {category_code}.")
        period = self.periods.get_active_by_code(period_code)
        if period is None:
            raise PeriodNotFoundError(f"Période inconnue ou inactive : {period_code}.")

        quote_lines: list[QuoteLine] = []
        for number in dict.fromkeys(line_numbers):  # doublons ignorés, ordre conservé
            line = self.lines.get_active_by_number(number)
            if line is None:
                raise InvalidLineError(f"Ligne inconnue ou inactive : {number}.")
            quote_lines.append(QuoteLine(line, self._line_price(category, period, line, on_date)))
        total = sum((ql.price for ql in quote_lines), ZERO).quantize(Decimal("0.001"))
        return Quote(category, period, quote_lines, total)

    def _line_price(self, category: Category, period: SubscriptionPeriod, line: Line, on_date: date) -> Decimal:
        if category.free_travel:
            return ZERO
        price = self.tariffs.get_applicable(category.id, line.id, period.id, on_date)
        if price is None:
            raise SubscriptionTariffNotFoundError(
                f"Aucun tarif d'abonnement pour la ligne {line.number}, la catégorie {category.code} "
                f"et la période {period.code} au {on_date.isoformat()}."
            )
        return price

    # ------------------------------------------------------------------ création

    def create_subscription(
        self, card: Card, category_code: str, period_code: str, line_numbers: list[str], start_date: date
    ) -> Subscription:
        """Crée un abonnement pour la carte (flush, sans commit).

        La durée vient de la période (ex. annuel : du 01/01/2026 au 31/12/2026). Le prix de chaque ligne est figé
        dans `subscription_lines.price` : un changement de tarif ultérieur ne modifie pas les abonnements existants.
        Une catégorie à gratuité totale peut n'avoir aucune ligne ; sinon au moins une ligne est requise.
        """
        quote = self.quote(category_code, period_code, line_numbers, start_date)
        if not quote.lines and not quote.category.free_travel:
            raise InvalidLineError("Un abonnement doit contenir au moins une ligne.")
        subscription = Subscription(
            card_id=card.id,
            category_id=quote.category.id,
            period_id=quote.period.id,
            valid_from=start_date,
            valid_until=end_of_period(start_date, quote.period.months),
            status=EntityStatus.ACTIVE.value,
        )
        subscription.subscription_lines = [SubscriptionLine(line_id=ql.line.id, price=ql.price) for ql in quote.lines]
        return self.subscriptions.add(subscription)

    def add_line(self, subscription: Subscription, line_number: str) -> Subscription:
        """Ajoute une ligne à un abonnement existant, au tarif applicable à sa date de début. Sans effet si déjà présente."""
        if any(sl.line.number == line_number for sl in subscription.subscription_lines):
            return subscription
        category = subscription.category
        period = subscription.period
        line = self.lines.get_active_by_number(line_number)
        if line is None:
            raise InvalidLineError(f"Ligne inconnue ou inactive : {line_number}.")
        price = self._line_price(category, period, line, subscription.valid_from)
        subscription.subscription_lines.append(SubscriptionLine(line_id=line.id, price=price))
        self.db.flush()
        return subscription
