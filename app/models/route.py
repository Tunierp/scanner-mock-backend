from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EntityStatus
from app.models.base import Base


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=EntityStatus.ACTIVE.value)
