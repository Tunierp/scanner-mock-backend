"""Lignes STS et tarifs chargés par `python -m app.seed`.

POUR AJOUTER UNE LIGNE : ajouter un tuple dans STS_LINES, puis relancer `python -m app.seed`
(idempotent : ne recrée pas ce qui existe). POUR AJOUTER UN TARIF : ajouter un tuple dans LINE_FARES.
Une ligne représente les DEUX sens ; un tarif est pour UN SEUL sens (pas un aller-retour).
"""
from datetime import date

# (numéro de ligne, ville de départ, ville de destination, arrêts intermédiaires ou None)
# Découpage du libellé « Sousse-A-B-C » : 1er = départ, dernier = destination, le reste = arrêts intermédiaires.
# Liste non exhaustive.
STS_LINES: list[tuple[str, str, str, str | None]] = [
    ("52A", "Sousse", "Monastir", None),
    ("52B", "Sousse", "Monastir", None),
    ("52C", "Sousse", "Monastir", None),
    ("28", "Sousse", "Messadine", None),
    ("6", "Sousse", "Riyadh 5", None),
    ("20", "Sousse", "Kalaa Seguira", None),
    ("15A", "Sousse", "Kalaa Kebira", None),
    ("15B", "Sousse", "Kalaa Kebira", None),
    ("15", "Sousse", "Kalaa Kebira", None),
    ("15C", "Sousse", "Kalaa Kebira", None),
    ("12/18", "Sousse", "Hergla", None),
    ("17", "Sousse", "Sidi Bou Ali", None),
    ("17/18", "Sousse", "Hergla", "Sidi Bou Ali"),
    ("8", "Sousse", "Ezzouhour", "Riyadh"),
    ("75", "Sousse", "Ouardanine", "Sahline"),
    ("58", "Sousse", "Sidi Ameur", "Môotmar"),
    ("5", "Sousse", "Quartier de Ghodrane", None),
    ("60", "Sousse", "Beni Hassen", "Masdour - Jammel"),
    ("61", "Sousse", "Jammel", None),
    ("62", "Sousse", "Zarremdine", "Bembla - Jammel"),
    ("23", "Sousse", "Menzel Kamel", None),
    ("24", "Sousse", "Ennagher", None),
    ("25", "Sousse", "Chiab", None),
    ("3", "Sousse", "Bouhssina", None),
    ("12", "Sousse", "Chott Mariem", "Kantaoui"),
    ("13C", "Sousse", "Sahloul", None),
    ("16", "Sousse", "Elfokaia", "Akouda - Chott Meriem"),
    ("22A", "Sousse", "Msaken", None),
    ("22B", "Sousse", "Msaken", None),
]

# (numéro de ligne, montant en TND pour UN sens, date de début de validité)
# Un tarif reste valable jusqu'au tarif suivant (la date de début de validité fait l'historique).
# Seule la ligne 22A a des tarifs pour l'instant (exemple fourni) : les autres lignes n'en ont pas encore.
LINE_FARES: list[tuple[str, str, date]] = [
    ("22A", "1.100", date(2023, 5, 12)),
    ("22A", "1.200", date(2025, 1, 1)),
]
