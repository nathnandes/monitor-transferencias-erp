from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import _created_at, _updated_at

if TYPE_CHECKING:
    from app.database.models.transferencias import Transferencia


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (UniqueConstraint("id_erp", "ambiente", name="uq_empresas_id_erp_ambiente"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    id_erp: Mapped[str | None] = mapped_column(String(50))

    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))

    bairro: Mapped[str | None] = mapped_column(String(100))

    cnpj: Mapped[str | None] = mapped_column(String(14), index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    ambiente: Mapped[str] = mapped_column(String(20), default="producao", server_default="producao")

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    transferencias_origem: Mapped[list["Transferencia"]] = relationship(
        back_populates="empresa_origem",
        foreign_keys="Transferencia.empresa_origem_id",
        passive_deletes="all",
    )
    transferencias_destino: Mapped[list["Transferencia"]] = relationship(
        back_populates="empresa_destino",
        foreign_keys="Transferencia.empresa_destino_id",
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"<Empresa {self.codigo} {self.nome!r}>"
