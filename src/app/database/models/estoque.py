from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import _created_at, _updated_at

if TYPE_CHECKING:
    from app.database.models.empresas import Empresa


def _saldo() -> Mapped[Decimal | None]:
    return mapped_column(Numeric(15, 3))


class EstoqueEmpresaLocalLote(Base):
    __tablename__ = "estoque_empresa_local_lote"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id",
            "id_produto",
            "id_subproduto",
            "id_local_estoque",
            "descricao_lote",
            name="uq_estoque_empresa_local_lote_chave",
        ),
        Index("ix_estoque_empresa_local_lote_produto", "id_produto", "id_subproduto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="RESTRICT"))

    id_produto: Mapped[str] = mapped_column(String(50))
    id_subproduto: Mapped[str] = mapped_column(String(50))
    id_local_estoque: Mapped[str] = mapped_column(String(50))
    descricao_local_estoque: Mapped[str | None] = mapped_column(String(200))
    utiliza_lote: Mapped[bool | None] = mapped_column(Boolean)

    descricao_lote: Mapped[str] = mapped_column(String(200), default="", server_default="")
    permite_estoque_negativo: Mapped[bool | None] = mapped_column(Boolean)

    saldo_atual: Mapped[Decimal | None] = _saldo()
    saldo_reservado: Mapped[Decimal | None] = _saldo()
    saldo_disponivel: Mapped[Decimal | None] = _saldo()

    data_alteracao_erp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    inativo_erp: Mapped[bool | None] = mapped_column(Boolean)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    ausencias_leitura_completa: Mapped[int] = mapped_column(default=0, server_default="0")
    removido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ultima_sincronizacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    empresa: Mapped["Empresa"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<EstoqueEmpresaLocalLote emp={self.empresa_id} {self.id_produto}/"
            f"{self.id_subproduto} local={self.id_local_estoque} {self.saldo_atual}>"
        )


class EstoqueConsolidado(Base):
    __tablename__ = "estoque_consolidado"
    __table_args__ = (
        UniqueConstraint("id_produto", "id_subproduto", name="uq_estoque_consolidado_produto"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_produto: Mapped[str] = mapped_column(String(50))
    id_subproduto: Mapped[str] = mapped_column(String(50))
    saldo_atual_total: Mapped[Decimal | None] = _saldo()
    saldo_reservado_total: Mapped[Decimal | None] = _saldo()
    saldo_disponivel_total: Mapped[Decimal | None] = _saldo()

    empresas_com_estoque: Mapped[int] = mapped_column(default=0, server_default="0")
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return (
            f"<EstoqueConsolidado {self.id_produto}/{self.id_subproduto} {self.saldo_atual_total}>"
        )


def _valor() -> Mapped[Decimal | None]:
    return mapped_column(Numeric(15, 6))


class Produto(Base):
    __tablename__ = "produtos"
    __table_args__ = (UniqueConstraint("id_produto", "id_subproduto", name="uq_produtos_produto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    id_produto: Mapped[str] = mapped_column(String(50))
    id_subproduto: Mapped[str] = mapped_column(String(50))
    descricao: Mapped[str | None] = mapped_column(String(200))
    descricao_resumida: Mapped[str | None] = mapped_column(String(100))
    referencia: Mapped[str | None] = mapped_column(String(50))
    codigo_barras: Mapped[str | None] = mapped_column(String(20))
    embalagem_saida: Mapped[str | None] = mapped_column(String(10))
    marca: Mapped[str | None] = mapped_column(String(100))
    divisao: Mapped[str | None] = mapped_column(String(100))
    secao: Mapped[str | None] = mapped_column(String(100))
    grupo: Mapped[str | None] = mapped_column(String(100))
    subgrupo: Mapped[str | None] = mapped_column(String(100))
    bloqueado_venda: Mapped[bool | None] = mapped_column(Boolean)
    inativo_erp: Mapped[bool | None] = mapped_column(Boolean)
    data_alteracao_erp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ultima_sincronizacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<Produto {self.id_produto}/{self.id_subproduto} {self.descricao}>"


class PrecoProdutoEmpresa(Base):
    __tablename__ = "precos_produto_empresa"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "id_produto", "id_subproduto", name="uq_precos_produto_empresa_chave"
        ),
        Index("ix_precos_produto_empresa_produto", "id_produto", "id_subproduto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="RESTRICT"))
    id_produto: Mapped[str] = mapped_column(String(50))
    id_subproduto: Mapped[str] = mapped_column(String(50))

    preco_varejo: Mapped[Decimal | None] = _valor()
    preco_promocao_varejo: Mapped[Decimal | None] = _valor()
    inicio_promocao_varejo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fim_promocao_varejo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preco_atacado: Mapped[Decimal | None] = _valor()
    preco_promocao_atacado: Mapped[Decimal | None] = _valor()
    inicio_promocao_atacado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fim_promocao_atacado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    custo_reposicao: Mapped[Decimal | None] = _valor()
    custo_gerencial: Mapped[Decimal | None] = _valor()
    custo_nota_fiscal: Mapped[Decimal | None] = _valor()

    data_alteracao_erp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inativo_erp: Mapped[bool | None] = mapped_column(Boolean)
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ultima_sincronizacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    empresa: Mapped["Empresa"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<PrecoProdutoEmpresa emp={self.empresa_id} {self.id_produto}/"
            f"{self.id_subproduto} varejo={self.preco_varejo}>"
        )


class ParametrosEstoqueBaixo(Base):
    __tablename__ = "parametros_estoque_baixo"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_parametros_estoque_baixo_uma_linha"),
        CheckConstraint(
            "dias_cobertura BETWEEN 1 AND 365", name="ck_parametros_estoque_baixo_dias"
        ),
        CheckConstraint("janela_dias BETWEEN 7 AND 180", name="ck_parametros_estoque_baixo_janela"),
        CheckConstraint(
            "cardinality(horarios) BETWEEN 1 AND 6", name="ck_parametros_estoque_baixo_horarios"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    dias_cobertura: Mapped[int] = mapped_column(Integer)
    dias_por_empresa: Mapped[dict[str, int]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    janela_dias: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    horarios: Mapped[list[str]] = mapped_column(ARRAY(String(5)))

    ultima_execucao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = _updated_at()


class EstoqueBaixoAvisado(Base):
    __tablename__ = "estoque_baixo_avisados"

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )
    id_produto: Mapped[str] = mapped_column(String(50), primary_key=True)
    id_subproduto: Mapped[str] = mapped_column(String(50), primary_key=True)
    avisado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExcecaoCobertura(Base):
    __tablename__ = "excecoes_cobertura"

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )
    id_produto: Mapped[str] = mapped_column(String(50), primary_key=True)
    id_subproduto: Mapped[str] = mapped_column(String(50), primary_key=True)
    motivo: Mapped[str | None] = mapped_column(String(200))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
