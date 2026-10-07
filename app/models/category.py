from sqlalchemy import Boolean, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EntityStatus
from app.models.base import Base


class Category(Base):
    """Catégorie générique : UNE SEULE table pour toutes les entités, la colonne `type` dit ce que la catégorie classe
    (`SUBSCRIPTION` : catégories d'abonnés Universitaire, Scolaire, Handicapé...; `USER`; `BUS`; ...).

    Nouveau type d'entité ou nouvelle catégorie = nouvelles lignes, jamais de nouvelle table. Les tables qui s'y
    réfèrent utilisent une clé étrangère composite (`category_id`, `category_type`) -> (`id`, `type`) avec un CHECK sur
    le type : la base garantit qu'un abonnement ne peut pas pointer vers une catégorie de type USER ou BUS.
    `free_travel` = gratuité sur toutes les lignes (catégorie d'abonnement Handicapé), règle configurable.
    """

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("type", "code", name="uq_categories_type_code"),
        UniqueConstraint("id", "type", name="uq_categories_id_type"),  # cible des clés étrangères composites
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    free_travel: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)
