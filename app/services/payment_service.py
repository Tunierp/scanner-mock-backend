"""PaymentService : unique point d'entrée de la logique métier.

Utilisé à la fois par POST /api/v1/scanner/payments et POST /api/v1/scanner/sync/transactions.

Ordre des règles pour une transaction :
  1. même scan déjà traité (device_id + transaction_id + occurred_at) -> DUPLICATE_TRANSACTION (409)
  2. carte inconnue                         -> CARD_NOT_FOUND (404)
  3. ligne inconnue ou inactive             -> INVALID_LINE (400)
     (le tarif n'est PAS envoyé par le scanner : il est lu en base, par ligne et par date du scan)
  4. carte non active (bloquée, expirée, perdue, remplacée, inactive) -> DECLINED (CARD_BLOCKED, CARD_EXPIRED,
     CARD_LOST, CARD_REPLACED, CARD_NOT_ACTIVE)
  5. même carte, même véhicule, même ligne, déjà validée dans la fenêtre de voyage
                                            -> DECLINED / TRIP_ALREADY_VALIDATED (aucun débit)
  6. abonnement d'une catégorie à gratuité totale (ex. Handicapé), valide -> APPROVED / FREE_TRAVEL_CATEGORY
     (toutes les lignes, aucun débit)
     abonnement valide qui contient la ligne -> APPROVED / VALID_SUBSCRIPTION (aucun débit)
  7. aucun tarif pour cette ligne à cette date -> FARE_NOT_FOUND (404, rien n'est enregistré)
     solde suffisant                        -> APPROVED / BALANCE_DEBITED
  8. solde insuffisant                      -> DECLINED / INSUFFICIENT_BALANCE (aucun débit)

Deux protections distinctes (ne pas les confondre) :
  * transaction_id  : protège contre le RENVOI d'une même requête (réseau instable, retry).
  * règle du voyage : protège contre un NOUVEAU scan de la même carte pour le même voyage.

Atomicité / concurrence : la ligne de la carte est verrouillée (SELECT ... FOR UPDATE), puis le doublon
et la règle du voyage sont vérifiés SOUS verrou, puis débit + insertion de la transaction sont commités
ensemble. La contrainte UNIQUE (device_id, transaction_id, occurred_at) est le filet de sécurité final.
"""
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    MESSAGES,
    CARD_STATUS_REASONS,
    CardStatus,
    PaymentMethod,
    ReasonCode,
    TransactionStatus,
)
from app.core.exceptions import (
    AppError,
    CardNotFoundError,
    DuplicateTransactionError,
    FareNotFoundError,
    InvalidLineError,
    TransactionAlreadyProcessedError,
)
from app.models.card import Card
from app.models.line import Line
from app.models.transaction import Transaction
from app.repositories.card_repository import CardRepository
from app.repositories.line_fare_repository import LineFareRepository
from app.repositories.line_repository import LineRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.transaction_repository import TransactionRepository

logger = logging.getLogger(__name__)

THREE_PLACES = Decimal("0.001")
DUPLICATE_CODES = {ReasonCode.DUPLICATE_TRANSACTION, ReasonCode.TRANSACTION_ALREADY_PROCESSED}


@dataclass(frozen=True)
class TransactionCommand:
    """Données d'un scan à traiter (identiques pour le temps réel et l'offline)."""

    transaction_id: str
    card_tag: str
    device_id: str
    vehicle_id: str
    line_number: str
    occurred_at: datetime


@dataclass
class PaymentResult:
    transaction_id: str
    status: TransactionStatus
    reason_code: ReasonCode
    message: str
    payment_method: PaymentMethod | None = None
    amount: Decimal | None = None
    balance_before: Decimal | None = None
    balance_after: Decimal | None = None
    balance: Decimal | None = None
    original_status: str | None = None
    original_reason_code: str | None = None

    def as_dict(self, *, as_float: bool = False, keep_null_payment_method: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
        }
        if self.payment_method is not None or keep_null_payment_method:
            data["payment_method"] = self.payment_method
        for name in ("amount", "balance_before", "balance_after", "balance"):
            value = getattr(self, name)
            if value is not None:
                data[name] = float(value) if as_float else value
        for name in ("original_status", "original_reason_code"):
            value = getattr(self, name)
            if value is not None:
                data[name] = value
        return data


@dataclass
class BatchResult:
    device_id: str
    total: int
    processed: int
    approved: int
    declined: int
    duplicates: int
    results: list[PaymentResult] = field(default_factory=list)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class PaymentService:
    def __init__(
        self,
        db: Session,
        cards: CardRepository,
        subscriptions: SubscriptionRepository,
        lines: LineRepository,
        fares: LineFareRepository,
        transactions: TransactionRepository,
        trip_window_minutes: int = 60,
        business_timezone: str = "Africa/Tunis",
    ):
        self.db = db
        self.cards = cards
        self.subscriptions = subscriptions
        self.lines = lines
        self.fares = fares
        self.transactions = transactions
        self.trip_window = timedelta(minutes=trip_window_minutes)
        self.local_tz = ZoneInfo(business_timezone)

    # ------------------------------------------------------------------ API publique

    def process_transaction(self, cmd: TransactionCommand) -> PaymentResult:
        """Traite un scan de façon atomique et idempotente.

        Lève une `AppError` (CARD_NOT_FOUND, INVALID_*, DUPLICATE_TRANSACTION, ...) quand le scan ne peut
        pas être traité ; retourne un `PaymentResult` (APPROVED ou DECLINED) sinon.
        """
        occurred_at = _to_utc(cmd.occurred_at)
        try:
            existing = self.transactions.get_by_scan(cmd.device_id, cmd.transaction_id, occurred_at)
            if existing is not None:
                raise self._duplicate_error(existing, cmd)
            result = self._process_new(cmd, occurred_at)
            self.db.commit()
            return result
        except IntegrityError:
            # Course perdue sur la contrainte UNIQUE(device_id, transaction_id, occurred_at) : une autre requête a inséré
            # le même scan entre-temps. Rien n'a été débité par cette requête.
            self.db.rollback()
            existing = self.transactions.get_by_scan(cmd.device_id, cmd.transaction_id, occurred_at)
            if existing is None:
                raise
            error = self._duplicate_error(existing, cmd)
            self.db.rollback()
            raise error from None
        except Exception:
            self.db.rollback()
            raise

    def process_batch(self, device_id: str, commands: Sequence[TransactionCommand]) -> BatchResult:
        """Synchronisation offline : chaque scan est traité indépendamment, dans l'ordre."""
        results = [self._process_safely(cmd) for cmd in commands]
        approved = sum(1 for r in results if r.status == TransactionStatus.APPROVED)
        duplicates = sum(1 for r in results if r.reason_code in DUPLICATE_CODES)
        declined = len(results) - approved - duplicates
        return BatchResult(
            device_id=device_id,
            total=len(results),
            processed=approved + declined,
            approved=approved,
            declined=declined,
            duplicates=duplicates,
            results=results,
        )

    # ------------------------------------------------------------------ logique interne

    def _process_safely(self, cmd: TransactionCommand) -> PaymentResult:
        try:
            return self.process_transaction(cmd)
        except (DuplicateTransactionError, TransactionAlreadyProcessedError) as exc:
            details = exc.details or {}
            return PaymentResult(
                transaction_id=cmd.transaction_id,
                status=TransactionStatus.DECLINED,
                reason_code=exc.code,
                message=exc.message,
                original_status=str(details.get("status")) if details.get("status") else None,
                original_reason_code=(
                    str(details.get("reason_code")) if details.get("reason_code") else None
                ),
            )
        except AppError as exc:
            return PaymentResult(
                transaction_id=cmd.transaction_id,
                status=TransactionStatus.DECLINED,
                reason_code=exc.code,
                message=exc.message,
            )
        except Exception:
            logger.exception("Erreur inattendue pendant le traitement de %s", cmd.transaction_id)
            return PaymentResult(
                transaction_id=cmd.transaction_id,
                status=TransactionStatus.DECLINED,
                reason_code=ReasonCode.INTERNAL_ERROR,
                message=MESSAGES[ReasonCode.INTERNAL_ERROR],
            )

    def _process_new(self, cmd: TransactionCommand, occurred_at: datetime) -> PaymentResult:
        # Verrou de ligne sur la carte : sérialise tous les traitements concernant cette carte.
        card = self.cards.get_by_tag(cmd.card_tag, for_update=True)
        if card is None:
            raise CardNotFoundError()

        # Re-vérification du doublon SOUS verrou (une requête concurrente a pu commiter entre-temps).
        existing = self.transactions.get_by_scan(cmd.device_id, cmd.transaction_id, occurred_at)
        if existing is not None:
            raise self._duplicate_error(existing, cmd)

        line = self.lines.get_active_by_number(cmd.line_number)
        if line is None:
            raise InvalidLineError()
        occurred_local_date = occurred_at.astimezone(self.local_tz).date()
        fare = self.fares.get_applicable(line.id, occurred_local_date)  # tarif d'UN sens, None si absent
        shown = fare if fare is not None else Decimal("0.000")  # montant « demandé » indiqué dans un refus

        if card.status != CardStatus.ACTIVE.value:
            reason = CARD_STATUS_REASONS.get(card.status, ReasonCode.CARD_BLOCKED)
            return self._record(card, line, cmd, fare, occurred_at, TransactionStatus.DECLINED, reason, None, shown)

        # Règle du voyage : le même voyageur ne peut pas être validé/débité deux fois pour le même voyage.
        # (vérifié sous le verrou de la carte -> deux scans simultanés ne peuvent pas passer tous les deux)
        previous = self.transactions.find_approved_trip_scan(
            card.id, cmd.vehicle_id, line.id, occurred_at, self.trip_window
        )
        if previous is not None:
            return self._record(
                card, line, cmd, fare, occurred_at, TransactionStatus.DECLINED,
                ReasonCode.TRIP_ALREADY_VALIDATED, None, shown,
            )

        # Catégorie à gratuité totale (ex. Handicapé) : toutes les lignes sont gratuites, quel que soit le tarif.
        if self.subscriptions.has_free_travel_subscription(card.id, occurred_local_date):
            return self._record(
                card, line, cmd, fare, occurred_at, TransactionStatus.APPROVED,
                ReasonCode.FREE_TRAVEL_CATEGORY, PaymentMethod.SUBSCRIPTION, Decimal("0.000"),
            )

        # Un abonnement couvre la ligne même si elle n'a pas (encore) de tarif.
        if self.subscriptions.has_valid_subscription_for_line(card.id, line.id, occurred_local_date):
            return self._record(
                card, line, cmd, fare, occurred_at, TransactionStatus.APPROVED,
                ReasonCode.VALID_SUBSCRIPTION, PaymentMethod.SUBSCRIPTION, Decimal("0.000"),
            )

        if fare is None:
            raise FareNotFoundError()

        balance_before = Decimal(card.balance).quantize(THREE_PLACES)
        if balance_before < fare:
            return self._record(
                card, line, cmd, fare, occurred_at, TransactionStatus.DECLINED,
                ReasonCode.INSUFFICIENT_BALANCE, None, fare,
                balance_before=balance_before, balance_after=balance_before,
            )

        balance_after = balance_before - fare
        self.cards.set_balance(card, balance_after)
        return self._record(
            card, line, cmd, fare, occurred_at, TransactionStatus.APPROVED,
            ReasonCode.BALANCE_DEBITED, PaymentMethod.CARD_BALANCE, fare,
            balance_before=balance_before, balance_after=balance_after,
        )

    def _record(
        self,
        card: Card,
        line: Line,
        cmd: TransactionCommand,
        fare: Decimal | None,
        occurred_at: datetime,
        status: TransactionStatus,
        reason: ReasonCode,
        method: PaymentMethod | None,
        amount: Decimal,
        *,
        balance_before: Decimal | None = None,
        balance_after: Decimal | None = None,
    ) -> PaymentResult:
        transaction = Transaction(
            transaction_id=cmd.transaction_id,
            card_id=card.id,
            device_id=cmd.device_id,
            vehicle_id=cmd.vehicle_id,
            line_id=line.id,
            fare_amount=fare,
            amount=amount,
            currency=card.currency,
            payment_method=method.value if method else None,
            status=status.value,
            reason_code=reason.value,
            occurred_at=occurred_at,
            processed_at=datetime.now(UTC),
            balance_before=balance_before,
            balance_after=balance_after,
        )
        self.transactions.add(transaction)  # flush : lève IntegrityError si doublon
        return self._to_result(transaction)

    @staticmethod
    def _to_result(tx: Transaction) -> PaymentResult:
        reason = ReasonCode(tx.reason_code)
        result = PaymentResult(
            transaction_id=tx.transaction_id,
            status=TransactionStatus(tx.status),
            reason_code=reason,
            message=MESSAGES[reason],
            payment_method=PaymentMethod(tx.payment_method) if tx.payment_method else None,
            amount=Decimal(tx.amount).quantize(THREE_PLACES),
        )
        if reason == ReasonCode.INSUFFICIENT_BALANCE and tx.balance_before is not None:
            result.balance = Decimal(tx.balance_before).quantize(THREE_PLACES)
        elif tx.payment_method == PaymentMethod.CARD_BALANCE.value:
            result.balance_before = Decimal(tx.balance_before).quantize(THREE_PLACES)
            result.balance_after = Decimal(tx.balance_after).quantize(THREE_PLACES)
        return result

    def _duplicate_error(self, existing: Transaction, cmd: TransactionCommand) -> AppError:
        """Construit l'erreur de doublon en conservant le résultat initial dans `details`."""
        original = self._to_result(existing)
        same_payload = (
            existing.card.card_tag == cmd.card_tag
            and existing.line.number == cmd.line_number
        )
        error_cls = DuplicateTransactionError if same_payload else TransactionAlreadyProcessedError
        return error_cls(details=original.as_dict(as_float=True))
