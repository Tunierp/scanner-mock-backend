"""Catégories, périodes et tarifs d'abonnement chargés par `python -m app.seed`.

Tout est configurable en base : pour ajouter une catégorie, une période ou un tarif, ajouter une entrée ici puis
relancer `python -m app.seed` (idempotent), ou faire un INSERT SQL. Aucune modification de structure n'est nécessaire.
"""
from datetime import date

# (code, nom, gratuité sur toutes les lignes ?)
CATEGORIES: list[tuple[str, str, bool]] = [
    ("UNIVERSITY", "Universitaire", False),
    ("SCHOOL", "Scolaire", False),
    ("DISABLED", "Handicapé", True),  # monte sur n'importe quelle ligne sans frais
    ("PASSENGER", "Passager", False),
    ("WORKER", "Travailleur", False),
    ("INTERN", "Stagiaire", False),
]

# (code, nom, durée en mois)
PERIODS: list[tuple[str, str, int]] = [
    ("MONTHLY", "Mensuel", 1),
    ("QUARTERLY", "Trimestriel", 3),
    ("SEMIANNUAL", "Semestriel", 6),
    ("ANNUAL", "Annuel", 12),
]

TARIFFS_FROM = date(2025, 1, 1)

# (numéro de ligne, catégorie, période, montant en TND, date de début de validité)
# ⚠ Seuls les montants de la ligne 22A (Sousse - Msaken : 31.000 / an, 16.000 / semestre) viennent de l'énoncé.
# Les autres montants sont des VALEURS DE TEST (non officielles), à remplacer par les vrais tarifs.
SUBSCRIPTION_TARIFFS: list[tuple[str, str, str, str, date]] = [
    ("22A", "PASSENGER", "ANNUAL", "31.000", TARIFFS_FROM),
    ("22A", "PASSENGER", "SEMIANNUAL", "16.000", TARIFFS_FROM),
    ("52A", "PASSENGER", "ANNUAL", "30.000", TARIFFS_FROM),  # valeur de test
    ("61", "PASSENGER", "ANNUAL", "25.000", TARIFFS_FROM),  # valeur de test
    ("13C", "UNIVERSITY", "ANNUAL", "20.000", TARIFFS_FROM),  # valeur de test
    ("16", "UNIVERSITY", "ANNUAL", "22.000", TARIFFS_FROM),  # valeur de test
]
