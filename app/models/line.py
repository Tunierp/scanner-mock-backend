from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EntityStatus
from app.models.base import Base


class Line(Base):
    """Ligne de transport, ex. « 22A - Sousse - Msaken ».

    Une ligne représente les DEUX sens (Sousse → Msaken et Msaken → Sousse). C'est la ligne EXPLOITÉE (le numéro
    que le scanner envoie) ; ce que l'on VEND dans un abonnement, ce sont des liaisons (`corridors`) qui regroupent des lignes.
    `via` = arrêts intermédiaires éventuels (texte libre).
    """

    __tablename__ = "lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    departure: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    via: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)

    fares: Mapped[list["LineFare"]] = relationship(back_populates="line", order_by="LineFare.valid_from")
    corridor_lines: Mapped[list["CorridorLine"]] = relationship(back_populates="line")  # noqa: F821

    @property
    def label(self) -> str:
        return f"{self.number} - {self.departure} - {self.destination}"


class LineFare(Base):
    """Tarif d'une ligne pour UN SEUL sens (pas un aller-retour), valable à partir de `valid_from`
    jusqu'au tarif suivant (historique des tarifs)."""

    __tablename__ = "line_fares"
    __table_args__ = (
        UniqueConstraint("line_id", "valid_from", name="uq_line_fares_line_valid_from"),
        CheckConstraint("amount > 0", name="ck_line_fares_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("lines.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    valid_from: Mapped[date] = mapped_column(Date)

    line: Mapped[Line] = relationship(back_populates="fares")
