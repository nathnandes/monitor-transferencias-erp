from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import _created_at, _in, _updated_at

if TYPE_CHECKING:
    from app.database.models.empresas import Empresa


class Venda(Base):
    __tablename__ = "vendas"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id_erp", name="uq_vendas_empresa_id_erp"),
        CheckConstraint("quantidade_itens >= 0", name="ck_vendas_quantidade_itens"),
        Index("ix_vendas_data_venda_empresa", "data_venda", "empresa_id"),
        Index("ix_vendas_id_vendedor", "id_vendedor"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="RESTRICT"))
    id_erp: Mapped[str] = mapped_column(String(50))

    numero_nota: Mapped[str | None] = mapped_column(String(20))
    serie: Mapped[str | None] = mapped_column(String(10))

    modelo: Mapped[str | None] = mapped_column(String(10))
    coi: Mapped[int] = mapped_column(Integer)

    canal: Mapped[str] = mapped_column(String(20), index=True)

    data_venda: Mapped[date] = mapped_column(Date)
    momento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelada: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    valor_desconto: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    quantidade_itens: Mapped[int] = mapped_column(Integer)
    id_vendedor: Mapped[str | None] = mapped_column(String(50))

    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    empresa: Mapped["Empresa"] = relationship()
    itens: Mapped[list["VendaItem"]] = relationship(
        back_populates="venda", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Venda {self.id_erp} {self.canal} {self.valor_total}>"


class Vendedor(Base):
    __tablename__ = "vendedores"

    id_erp: Mapped[str] = mapped_column(String(50), primary_key=True)
    nome: Mapped[str | None] = mapped_column(String(200))
    consultado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Vendedor {self.id_erp} {self.nome}>"


class VendaItem(Base):
    __tablename__ = "vendas_itens"
    __table_args__ = (Index("ix_vendas_itens_produto", "id_produto", "id_subproduto"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    venda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vendas.id", ondelete="CASCADE"), index=True
    )

    sequencia: Mapped[str | None] = mapped_column(String(20))
    id_produto: Mapped[str] = mapped_column(String(50))
    id_subproduto: Mapped[str | None] = mapped_column(String(50))
    descricao_produto: Mapped[str | None] = mapped_column(String(300))
    cfop: Mapped[str | None] = mapped_column(String(10))

    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    valor_liquido: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    valor_desconto: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    venda: Mapped[Venda] = relationship(back_populates="itens")

    def __repr__(self) -> str:
        return f"<VendaItem {self.id_produto} {self.quantidade}>"


class VendaDia(Base):
    __tablename__ = "vendas_dias"

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )
    dia: Mapped[date] = mapped_column(Date, primary_key=True)
    notas: Mapped[int] = mapped_column(Integer)
    versao: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sincronizacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="SET NULL")
    )

    def __repr__(self) -> str:
        return f"<VendaDia {self.empresa_id} {self.dia}>"


class VendaTitulo(Base):
    __tablename__ = "vendas_titulos"
    __table_args__ = (
        Index("ix_vendas_titulos_lancamento", "empresa_id", "dia_lancamento"),
        Index("ix_vendas_titulos_pagamento", "empresa_id", "dia_pagamento"),
    )

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )

    id_planilha: Mapped[str] = mapped_column(String(50), primary_key=True)
    id_titulo: Mapped[str] = mapped_column(String(20), primary_key=True)
    parcela: Mapped[str] = mapped_column(String(10), primary_key=True)

    id_forma: Mapped[int] = mapped_column(Integer)
    forma: Mapped[str] = mapped_column(String(60))
    dia_lancamento: Mapped[date] = mapped_column(Date)
    vencimento: Mapped[date | None] = mapped_column(Date)

    dia_pagamento: Mapped[date | None] = mapped_column(Date)
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    valor_pago: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    valor_pendente: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    juros: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    desconto: Mapped[Decimal] = mapped_column(Numeric(18, 2))

    def __repr__(self) -> str:
        return f"<VendaTitulo {self.dia_lancamento} {self.forma} {self.valor}>"


class Devolucao(Base):
    __tablename__ = "devolucoes"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id_erp", name="uq_devolucoes_empresa_id_erp"),
        Index("ix_devolucoes_data_empresa", "data_devolucao", "empresa_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="RESTRICT"))
    id_erp: Mapped[str] = mapped_column(String(50))
    numero_nota: Mapped[str | None] = mapped_column(String(20))
    coi: Mapped[int] = mapped_column(Integer)
    data_devolucao: Mapped[date] = mapped_column(Date)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    quantidade_itens: Mapped[int] = mapped_column(Integer)
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Devolucao {self.id_erp} {self.valor_total}>"


NIVEIS_META = ("GRUPO", "EMPRESA", "VENDEDOR")
PERIODOS_META = ("DIA", "SEMANA", "MES")


class MetaVenda(Base):
    __tablename__ = "metas_vendas"
    __table_args__ = (
        CheckConstraint(_in("nivel", NIVEIS_META), name="ck_metas_vendas_nivel"),
        CheckConstraint(_in("periodo", PERIODOS_META), name="ck_metas_vendas_periodo"),
        CheckConstraint("valor > 0", name="ck_metas_vendas_valor"),
        CheckConstraint(
            "(nivel = 'GRUPO' AND empresa_id IS NULL AND id_vendedor IS NULL)"
            " OR (nivel = 'EMPRESA' AND empresa_id IS NOT NULL AND id_vendedor IS NULL)"
            " OR (nivel = 'VENDEDOR' AND empresa_id IS NULL AND id_vendedor IS NOT NULL)",
            name="ck_metas_vendas_alvo",
        ),
        CheckConstraint(
            "referencia IS NULL OR periodo = 'DIA'"
            " OR (periodo = 'SEMANA' AND extract(isodow FROM referencia) = 1)"
            " OR (periodo = 'MES' AND extract(day FROM referencia) = 1)",
            name="ck_metas_vendas_referencia",
        ),
        Index(
            "uq_metas_vendas_alvo_periodo",
            "nivel",
            "empresa_id",
            "id_vendedor",
            "periodo",
            "referencia",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nivel: Mapped[str] = mapped_column(String(10))
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )

    id_vendedor: Mapped[str | None] = mapped_column(String(50))
    periodo: Mapped[str] = mapped_column(String(10))
    referencia: Mapped[date | None] = mapped_column(Date)
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = _updated_at()

    empresa: Mapped["Empresa | None"] = relationship()

    def __repr__(self) -> str:
        return f"<MetaVenda {self.nivel} {self.periodo} {self.valor}>"


class ParametrosMetas(Base):
    __tablename__ = "parametros_metas"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_parametros_metas_uma_linha"),
        CheckConstraint(
            "cardinality(marcos) BETWEEN 1 AND 10 AND 0 < ALL(marcos) AND 1000 >= ALL(marcos)",
            name="ck_parametros_metas_marcos",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    marcos: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = _updated_at()


class MetaAviso(Base):
    __tablename__ = "metas_avisos"

    meta_id: Mapped[int] = mapped_column(
        ForeignKey("metas_vendas.id", ondelete="CASCADE"), primary_key=True
    )
    periodo_inicio: Mapped[date] = mapped_column(Date, primary_key=True)
    marco: Mapped[int] = mapped_column(Integer, primary_key=True)
    avisado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
