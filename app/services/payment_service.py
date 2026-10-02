"""PaymentService : unique point d'entrée de la logique métier.

Utilisé à la fois par POST /api/v1/scanner/payments et POST /api/v1/scanner/sync/transactions.

Ordre des règles pour une transaction :
  1. transaction_id déjà connu         -> DUPLICATE_TRANSACTION (409, rien n'est retraité)
  2. carte inconnue                    -> CARD_NOT_FOUND (404)
  3. tarif / devise / ligne invalides  -> INVALID_FARE / INVALID_ROUTE (400)
  4. carte bloquée / expirée           -> DECLINED (CARD_BLOCKED / CARD_EXPIRED)
  5. abonnement valide pour la ligne   -> APPROVED / VALID_SUBSCRIPTION (aucun débit)
  6. solde suffisant                   -> APPROVED / BALANCE_DEBITED
  7. solde insuffisant                 -> DECLINED / INSUFFICIENT_BALANCE (aucun débit)

Atomicité / concurrence : la ligne de la carte est verrouillée (SELECT ... FOR UPDATE), puis la
vérification du doublon est refaite sous verrou, puis débit + insertion de la transaction sont
commités ensemble. La contrainte UNIQUE sur transactions.transaction_id est le filet de sécurité final.
"""
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    MAX_FARE,
    MESSAGES,
    CardStatus,
    PaymentMethod,
    ReasonCode,
    TransactionStatus,
)
from app.core.exceptions import (
    AppError,
    CardNotFoundError,
    DuplicateTransactionError,
    InvalidFareError,
    InvalidRouteError,
    TransactionAlreadyProcessedError,
)
from app.models.card import Card
from app.models.transaction import Transaction
from app.repositories.card_repository import CardRepository
from app.repositories.route_repository import RouteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.transaction_repository import TransactionRepository

logger = logging.getLogger(__name__)

THREE_PLACES = Decimal("0.001")
DUPLICATE_CODES = {ReasonCode.DUPLICATE_TRANSACTION, ReasonCode.TRANSACTION_ALREADY_PROCESSED}


@dataclass(frozen=True)
class TransactionCommand:
    """Données d'une transaction à traiter (identiques pour le temps réel et l'offline)."""

    transaction_id: str
    card_token: str
    device_id: str
    vehicle_id: str
    route_id: str
    fare: Decimal
    currency: str
    occurred_at: datetime


@dataclass
class PaymentResult:
    transaction_id: str
    status: TransactionStatus
    reason_code: ReasonCode
    message: str
    payment_method: PaymentMethod | None = None
    amount: Decimal | None = None
    currency: str | None = None
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
        for name in ("currency", "original_status", "original_reason_code"):
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
        routes: RouteRepository,
        transactions: TransactionRepository,
    ):
        self.db = db
        self.cards = cards
        self.subscriptions = subscriptions
        self.routes = routes
        self.transactions = transactions

    # ------------------------------------------------------------------ API publique

    def process_transaction(self, cmd: TransactionCommand) -> PaymentResult:
        """Traite une transaction de façon atomique et idempotente.

        Lève une `AppError` (CARD_NOT_FOUND, INVALID_*, DUPLICATE_TRANSACTION, ...) quand la
        transaction ne peut pas être traitée ; retourne un `PaymentResult` (APPROVED ou DECLINED)
        sinon.
        """
        try:
            existing = self.transactions.get_by_transaction_id(cmd.transaction_id)
            if existing is not None:
                raise self._duplicate_error(existing, cmd)
            result = self._process_new(cmd)
            self.db.commit()
            return result
        except IntegrityError:
            # Course perdue sur la contrainte UNIQUE(transaction_id) : un autre processus a inséré
            # la même transaction entre-temps. Rien n'a été débité par cette requête.
            self.db.rollback()
            existing = self.transactions.get_by_transaction_id(cmd.transaction_id)
            if existing is None:
                raise
            error = self._duplicate_error(existing, cmd)
            self.db.rollback()
            raise error from None
        except Exception:
            self.db.rollback()
            raise

    def process_batch(self, device_id: str, commands: Sequence[TransactionCommand]) -> BatchResult:
        """Synchronisation offline : chaque transaction est traitée indépendamment, dans l'ordre."""
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

    def _process_new(self, cmd: TransactionCommand) -> PaymentResult:
        # Verrou de ligne sur la carte : sérialise tous les traitements concernant cette carte.
        card = self.cards.get_by_token(cmd.card_token, for_update=True)
        if card is None:
            raise CardNotFoundError()

        # Re-vérification du doublon SOUS verrou (une requête concurrente a pu commiter entre-temps).
        existing = self.transactions.get_by_transaction_id(cmd.transaction_id)
        if existing is not None:
            raise self._duplicate_error(existing, cmd)

        fare = self._validate_fare(cmd, card)
        if self.routes.get_active_by_code(cmd.route_id) is None:
            raise InvalidRouteError()
        occurred_at = _to_utc(cmd.occurred_at)

        if card.status != CardStatus.ACTIVE.value:
            reason = ReasonCode.CARD_EXPIRED if card.status == CardStatus.EXPIRED.value else ReasonCode.CARD_BLOCKED
            return self._record(card, cmd, fare, occurred_at, TransactionStatus.DECLINED, reason, None, fare)

        if self.subscriptions.has_valid_subscription_for_route(card.id, cmd.route_id, occurred_at):
            return self._record(
                card, cmd, fare, occurred_at, TransactionStatus.APPROVED,
                ReasonCode.VALID_SUBSCRIPTION, PaymentMethod.SUBSCRIPTION, Decimal("0.000"),
            )

        balance_before = Decimal(card.balance).quantize(THREE_PLACES)
        if balance_before < fare:
            return self._record(
                card, cmd, fare, occurred_at, TransactionStatus.DECLINED,
                ReasonCode.INSUFFICIENT_BALANCE, None, fare,
                balance_before=balance_before, balance_after=balance_before,
            )

        balance_after = balance_before - fare
        self.cards.set_balance(card, balance_after)
        return self._record(
            card, cmd, fare, occurred_at, TransactionStatus.APPROVED,
            ReasonCode.BALANCE_DEBITED, PaymentMethod.CARD_BALANCE, fare,
            balance_before=balance_before, balance_after=balance_after,
        )

    @staticmethod
    def _validate_fare(cmd: TransactionCommand, card: Card) -> Decimal:
        fare = cmd.fare
        if not fare.is_finite() or fare <= 0 or fare > MAX_FARE:
            raise InvalidFareError("Le tarif doit être strictement positif.")
        if fare != fare.quantize(THREE_PLACES):
            raise InvalidFareError("Le tarif ne peut pas avoir plus de 3 décimales.")
        if cmd.currency.upper() != card.currency:
            raise InvalidFareError(f"Devise invalide : {card.currency} attendu.")
        return fare.quantize(THREE_PLACES)

    def _record(
        self,
        card: Card,
        cmd: TransactionCommand,
        fare: Decimal,
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
            route_id=cmd.route_id,
            fare=fare,
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
            currency=tx.currency,
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
            existing.card.card_token == cmd.card_token
            and existing.route_id == cmd.route_id
            and existing.fare == cmd.fare
        )
        error_cls = DuplicateTransactionError if same_payload else TransactionAlreadyProcessedError
        return error_cls(details=original.as_dict(as_float=True))
