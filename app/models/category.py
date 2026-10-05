from sqlalchemy import Boolean, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EntityStatus
from app.models.base import Base


class Category(Base):
    """Catégorie d'abonné (Universitaire, Scolaire, Handicapé, Passager, Travailleur, Stagiaire...).

    Extensible : ajouter une catégorie = ajouter une ligne. `free_travel` = gratuité sur TOUTES les lignes
    (c'est le cas de la catégorie Handicapé) : règle configurable, pas codée en dur sur un nom de catégorie.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    free_travel: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)
