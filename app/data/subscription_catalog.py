"""Catégories, périodes, liaisons (corridors) et tarifs d'abonnement chargés par `python -m app.seed`.

Tout est configurable en base : pour ajouter une catégorie, une période, une liaison ou un tarif, ajouter une entrée
ici puis relancer `python -m app.seed` (idempotent), ou faire un INSERT SQL. Aucune modification de structure.
"""
from datetime import date

from app.core.constants import CategoryType

# (type, code, nom, gratuité sur toutes les lignes ?) — une seule table `categories`, la colonne `type` dit ce qu'elle classe.
# Seul le type SUBSCRIPTION est utilisé pour l'instant ; ajouter ("USER", ...) ou ("BUS", ...) ne demande aucune nouvelle table.
CATEGORIES: list[tuple[CategoryType, str, str, bool]] = [
    (CategoryType.SUBSCRIPTION, "UNIVERSITY", "Universitaire", False),
    (CategoryType.SUBSCRIPTION, "SCHOOL", "Scolaire", False),
    (CategoryType.SUBSCRIPTION, "DISABLED", "Handicapé", True),  # monte sur n'importe quelle ligne sans frais
    (CategoryType.SUBSCRIPTION, "PASSENGER", "Passager", False),
    (CategoryType.SUBSCRIPTION, "WORKER", "Travailleur", False),
    (CategoryType.SUBSCRIPTION, "INTERN", "Stagiaire", False),
]

# (code, nom, durée en mois)
PERIODS: list[tuple[str, str, int]] = [
    ("MONTHLY", "Mensuel", 1),
    ("QUARTERLY", "Trimestriel", 3),
    ("SEMIANNUAL", "Semestriel", 6),
    ("ANNUAL", "Annuel", 12),
]

# Liaisons VENDUES dans les abonnements : (code, nom, départ, destination, numéros des lignes qui la desservent).
# Une liaison est facturée une fois, quel que soit le nombre de lignes (bus) qui la desservent ; une ligne peut desservir
# plusieurs liaisons. ⚠ Données de départ à compléter avec la réalité du réseau STS.
CORRIDORS: list[tuple[str, str, str, str, list[str]]] = [
    ("SOUSSE-MSAKEN", "Sousse - Msaken", "Sousse", "Msaken", ["22A", "22B"]),
    ("SOUSSE-MONASTIR", "Sousse - Monastir", "Sousse", "Monastir", ["52A", "52B", "52C"]),
    ("SOUSSE-SAHLOUL", "Sousse - Sahloul", "Sousse", "Sahloul", ["13C"]),
    ("SOUSSE-AKOUDA", "Sousse - Akouda", "Sousse", "Akouda", ["16"]),  # la ligne 16 passe par Akouda
    ("SOUSSE-JAMMEL", "Sousse - Jammel", "Sousse", "Jammel", ["61"]),
    # Hammam Sousse : desservie aussi par des bus d'un trajet plus large (Kalaa Kebira : 15*, Sidi Bou Ali : 17, 17/18)
    ("SOUSSE-HAMMAM-SOUSSE", "Sousse - Hammam Sousse", "Sousse", "Hammam Sousse",
     ["15", "15A", "15B", "15C", "17", "17/18"]),
]

FARES_FROM = date(2025, 1, 1)

# (code de la liaison, catégorie, période, montant en TND, date de début de validité)
# ⚠ Viennent de l'énoncé : Sousse - Msaken 31.000 / an et 16.000 / semestre ; Sousse - Hammam Sousse 30.000 / an et
# 15.000 / semestre (catégorie Passager supposée). Les autres montants sont des VALEURS DE TEST (non officielles).
SUBSCRIPTION_FARES: list[tuple[str, str, str, str, date]] = [
    ("SOUSSE-MSAKEN", "PASSENGER", "ANNUAL", "31.000", FARES_FROM),
    ("SOUSSE-MSAKEN", "PASSENGER", "SEMIANNUAL", "16.000", FARES_FROM),
    ("SOUSSE-HAMMAM-SOUSSE", "PASSENGER", "ANNUAL", "30.000", FARES_FROM),
    ("SOUSSE-HAMMAM-SOUSSE", "PASSENGER", "SEMIANNUAL", "15.000", FARES_FROM),
    ("SOUSSE-MONASTIR", "PASSENGER", "ANNUAL", "30.000", FARES_FROM),  # valeur de test
    ("SOUSSE-JAMMEL", "PASSENGER", "ANNUAL", "25.000", FARES_FROM),  # valeur de test
    ("SOUSSE-SAHLOUL", "UNIVERSITY", "ANNUAL", "20.000", FARES_FROM),  # valeur de test
    ("SOUSSE-AKOUDA", "UNIVERSITY", "ANNUAL", "22.000", FARES_FROM),  # valeur de test
]
