from datetime import date, datetime
from decimal import Decimal

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.comum import _created_at, _in, _updated_at
from app.dominio.operacoes_estoque import CATEGORIAS


class MovimentoEstoque(Base):
    __tablename__ = "movimentos_estoque"
    __table_args__ = (
        CheckConstraint(_in("tipo", CATEGORIAS), name="ck_movimentos_estoque_tipo"),
        Index("ix_movimentos_estoque_dia_empresa", "dia", "empresa_id"),
        Index("ix_movimentos_estoque_produto", "id_produto", "id_subproduto"),
        Index("ix_movimentos_estoque_subproduto", "id_subproduto"),
        Index("ix_movimentos_estoque_coi_dia_empresa", "coi", "dia", "empresa_id"),
        Index(
            "ix_movimentos_estoque_empresa_produto_dia",
            "empresa_id",
            "id_produto",
            "id_subproduto",
            "dia",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="RESTRICT"))

    dia: Mapped[date] = mapped_column(Date)
    coi: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(30))

    operacao: Mapped[str | None] = mapped_column(String(100))

    id_planilha: Mapped[str] = mapped_column(String(50))
    sequencia: Mapped[str | None] = mapped_column(String(20))
    id_produto: Mapped[str] = mapped_column(String(50))

    id_subproduto: Mapped[str] = mapped_column(String(50))

    descricao_produto: Mapped[str | None] = mapped_column(String(300))

    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<MovimentoEstoque {self.tipo} {self.id_produto} {self.quantidade}>"


class MovimentoEstoqueDia(Base):
    __tablename__ = "movimentos_estoque_dias"

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )
    dia: Mapped[date] = mapped_column(Date, primary_key=True)
    movimentos: Mapped[int] = mapped_column(Integer)
    versao: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sincronizacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="SET NULL")
    )

    def __repr__(self) -> str:
        return f"<MovimentoEstoqueDia {self.empresa_id} {self.dia}>"


class NotaMovimento(Base):
    __tablename__ = "notas_movimento"
    __table_args__ = (
        Index(
            "ix_notas_movimento_cnpj_destinatario",
            "cnpj_destinatario",
            postgresql_where="cnpj_destinatario IS NOT NULL",
        ),
    )

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )
    id_planilha: Mapped[str] = mapped_column(String(50), primary_key=True)
    saida: Mapped[bool] = mapped_column(Boolean)
    encontrado: Mapped[bool] = mapped_column(Boolean)
    numero: Mapped[str | None] = mapped_column(String(20))

    momento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usuario: Mapped[str | None] = mapped_column(String(100))
    cnpj_destinatario: Mapped[str | None] = mapped_column(String(14))
    nome_destinatario: Mapped[str | None] = mapped_column(String(200))
    cancelada: Mapped[bool | None] = mapped_column(Boolean)
    destinatario_lido: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cnpj_emitente: Mapped[str | None] = mapped_column(String(14))
    nome_emitente: Mapped[str | None] = mapped_column(String(200))
    emitente_lido: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<NotaMovimento {self.empresa_id} {self.id_planilha}>"


class JustificativaAvulsa(Base):
    __tablename__ = "justificativas_avulsas"

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )
    id_planilha: Mapped[str] = mapped_column(String(50), primary_key=True)
    motivo: Mapped[str] = mapped_column(String(30))
    observacao: Mapped[str | None] = mapped_column(Text)

    pelo_vinculo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    usuario_nome: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<JustificativaAvulsa {self.empresa_id} {self.id_planilha} {self.motivo}>"


class VinculoAvulsa(Base):
    __tablename__ = "vinculos_avulsas"
    __table_args__ = (
        UniqueConstraint("empresa_id", "saida_id_planilha", name="uq_vinculos_avulsas_saida"),
    )

    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True
    )
    entrada_id_planilha: Mapped[str] = mapped_column(String(50), primary_key=True)
    saida_id_planilha: Mapped[str] = mapped_column(String(50))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = _created_at()

    def __repr__(self) -> str:
        e, s = self.entrada_id_planilha, self.saida_id_planilha
        return f"<VinculoAvulsa {self.empresa_id} {e}<->{s}>"


class ParametrosAvulsas(Base):
    __tablename__ = "parametros_avulsas"
    __table_args__ = (CheckConstraint("id = 1", name="ck_parametros_avulsas_uma_linha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    justificar_desde: Mapped[date | None] = mapped_column(Date)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<ParametrosAvulsas desde={self.justificar_desde}>"
