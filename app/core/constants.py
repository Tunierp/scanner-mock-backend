"""Constantes métier centralisées : statuts, méthodes de paiement, codes et messages."""
from enum import StrEnum


class TransactionStatus(StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class PaymentMethod(StrEnum):
    SUBSCRIPTION = "SUBSCRIPTION"
    CARD_BALANCE = "CARD_BALANCE"


class CardStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"


class EntityStatus(StrEnum):
    """Statut générique (abonnement, ligne, lien carte/abonnement)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ReasonCode(StrEnum):
    # Codes métier
    VALID_SUBSCRIPTION = "VALID_SUBSCRIPTION"
    BALANCE_DEBITED = "BALANCE_DEBITED"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    CARD_NOT_FOUND = "CARD_NOT_FOUND"
    CARD_BLOCKED = "CARD_BLOCKED"
    CARD_EXPIRED = "CARD_EXPIRED"
    INVALID_ROUTE = "INVALID_ROUTE"
    INVALID_FARE = "INVALID_FARE"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    TRANSACTION_ALREADY_PROCESSED = "TRANSACTION_ALREADY_PROCESSED"
    TRIP_ALREADY_VALIDATED = "TRIP_ALREADY_VALIDATED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # Codes techniques (erreurs HTTP génériques)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    HTTP_ERROR = "HTTP_ERROR"


MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.VALID_SUBSCRIPTION: "Voyage couvert par l'abonnement.",
    ReasonCode.BALANCE_DEBITED: "Paiement accepté.",
    ReasonCode.INSUFFICIENT_BALANCE: "Solde insuffisant.",
    ReasonCode.CARD_NOT_FOUND: "Carte introuvable.",
    ReasonCode.CARD_BLOCKED: "Carte bloquée.",
    ReasonCode.CARD_EXPIRED: "Carte expirée.",
    ReasonCode.INVALID_ROUTE: "Ligne invalide ou inactive.",
    ReasonCode.INVALID_FARE: "Tarif invalide.",
    ReasonCode.DUPLICATE_TRANSACTION: "Transaction déjà traitée (doublon). Le résultat initial est conservé.",
    ReasonCode.TRANSACTION_ALREADY_PROCESSED: (
        "Ce scan (même scanner, même transaction_id, même heure) a déjà été traité avec des données différentes."
    ),
    ReasonCode.TRIP_ALREADY_VALIDATED: "Votre voyage est déjà payé/validé.",
    ReasonCode.INTERNAL_ERROR: "Erreur interne du serveur.",
    ReasonCode.VALIDATION_ERROR: "Requête invalide.",
    ReasonCode.NOT_FOUND: "Ressource introuvable.",
    ReasonCode.HTTP_ERROR: "Erreur HTTP.",
}

# Le tarif est exprimé avec 3 décimales maximum (dinar tunisien : millimes).
MONEY_DECIMALS = 3
MAX_FARE = 1000

# Devise interne (non exposée par l'API) : toutes les cartes sont en dinar tunisien.
DEFAULT_CURRENCY = "TND"
