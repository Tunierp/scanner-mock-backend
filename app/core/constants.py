"""Constantes métier centralisées : statuts, méthodes de paiement, codes et messages."""
from enum import StrEnum


class TransactionStatus(StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class PaymentMethod(StrEnum):
    SUBSCRIPTION = "SUBSCRIPTION"
    CARD_BALANCE = "CARD_BALANCE"


class CardStatus(StrEnum):
    """États d'une carte. Une seule carte ACTIVE par utilisateur (contrainte en base)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"  # non active
    LOST = "LOST"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"
    REPLACED = "REPLACED"


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
    CARD_NOT_ACTIVE = "CARD_NOT_ACTIVE"
    CARD_LOST = "CARD_LOST"
    CARD_REPLACED = "CARD_REPLACED"
    FREE_TRAVEL_CATEGORY = "FREE_TRAVEL_CATEGORY"
    INVALID_LINE = "INVALID_LINE"
    FARE_NOT_FOUND = "FARE_NOT_FOUND"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    TRANSACTION_ALREADY_PROCESSED = "TRANSACTION_ALREADY_PROCESSED"
    TRIP_ALREADY_VALIDATED = "TRIP_ALREADY_VALIDATED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # Gestion des utilisateurs / cartes / abonnements (services métier)
    ACTIVE_CARD_ALREADY_EXISTS = "ACTIVE_CARD_ALREADY_EXISTS"
    CATEGORY_NOT_FOUND = "CATEGORY_NOT_FOUND"
    PERIOD_NOT_FOUND = "PERIOD_NOT_FOUND"
    SUBSCRIPTION_TARIFF_NOT_FOUND = "SUBSCRIPTION_TARIFF_NOT_FOUND"
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
    ReasonCode.CARD_NOT_ACTIVE: "Carte non active.",
    ReasonCode.CARD_LOST: "Carte déclarée perdue.",
    ReasonCode.CARD_REPLACED: "Carte remplacée par une nouvelle carte.",
    ReasonCode.FREE_TRAVEL_CATEGORY: "Voyage gratuit pour cette catégorie d'abonné.",
    ReasonCode.INVALID_LINE: "Ligne inconnue ou inactive.",
    ReasonCode.FARE_NOT_FOUND: "Aucun tarif n'est défini pour cette ligne à cette date.",
    ReasonCode.DUPLICATE_TRANSACTION: "Transaction déjà traitée (doublon). Le résultat initial est conservé.",
    ReasonCode.TRANSACTION_ALREADY_PROCESSED: (
        "Ce scan (même scanner, même transaction_id, même heure) a déjà été traité avec des données différentes."
    ),
    ReasonCode.TRIP_ALREADY_VALIDATED: "Votre voyage est déjà payé/validé.",
    ReasonCode.INTERNAL_ERROR: "Erreur interne du serveur.",
    ReasonCode.ACTIVE_CARD_ALREADY_EXISTS: "Cet utilisateur possède déjà une carte active.",
    ReasonCode.CATEGORY_NOT_FOUND: "Catégorie inconnue ou inactive.",
    ReasonCode.PERIOD_NOT_FOUND: "Période d'abonnement inconnue ou inactive.",
    ReasonCode.SUBSCRIPTION_TARIFF_NOT_FOUND: "Aucun tarif d'abonnement défini pour cette combinaison catégorie + ligne + période.",
    ReasonCode.VALIDATION_ERROR: "Requête invalide.",
    ReasonCode.NOT_FOUND: "Ressource introuvable.",
    ReasonCode.HTTP_ERROR: "Erreur HTTP.",
}

# Refus d'un scan selon l'état de la carte (tout état non listé -> CARD_BLOCKED).
CARD_STATUS_REASONS: dict[str, ReasonCode] = {
    CardStatus.BLOCKED.value: ReasonCode.CARD_BLOCKED,
    CardStatus.EXPIRED.value: ReasonCode.CARD_EXPIRED,
    CardStatus.LOST.value: ReasonCode.CARD_LOST,
    CardStatus.REPLACED.value: ReasonCode.CARD_REPLACED,
    CardStatus.INACTIVE.value: ReasonCode.CARD_NOT_ACTIVE,
}

# Les montants sont exprimés en TND avec 3 décimales (millimes).
MONEY_DECIMALS = 3

# Devise interne (non exposée par l'API) : toutes les cartes sont en dinar tunisien.
DEFAULT_CURRENCY = "TND"
