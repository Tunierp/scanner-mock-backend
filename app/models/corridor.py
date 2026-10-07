from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EntityStatus
from app.models.base import Base


class Corridor(Base):
    """Liaison (axe) VENDUE dans un abonnement, ex. « Sousse - Msaken » : deux sens, une seule fois facturée,
    quel que soit le nombre de lignes (bus 22A, 22B...) qui la desservent.

    Les lignes qui la desservent sont listées dans `corridor_lines` : une ligne peut desservir plusieurs liaisons
    (ex. un bus Sousse - Kalaa Kebira qui passe par Hammam Sousse dessert aussi « Sousse - Hammam Sousse »).
    """

    __tablename__ = "corridors"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    departure: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)

    corridor_lines: Mapped[list["CorridorLine"]] = relationship(
        back_populates="corridor", cascade="all, delete-orphan"
    )

    @property
    def lines(self) -> list["Line"]:  # noqa: F821
        return [cl.line for cl in self.corridor_lines]


class CorridorLine(Base):
    """Many-to-Many liaison <-> ligne : quelles lignes (bus) desservent quelle liaison."""

    __tablename__ = "corridor_lines"

    corridor_id: Mapped[int] = mapped_column(ForeignKey("corridors.id"), primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("lines.id"), primary_key=True)

    corridor: Mapped[Corridor] = relationship(back_populates="corridor_lines")
    line: Mapped["Line"] = relationship(back_populates="corridor_lines")  # noqa: F821
