from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.database.models import (
    TIPOS_SINCRONIZACAO_MANUAL,
    EstoqueConsolidado,
    EstoqueEmpresaLocalLote,
    IntegracaoErro,
    Sincronizacao,
    SolicitacaoSincronizacao,
)


class TipoInvalidoError(ValueError):
    pass


def _validar_tipo(tipo: str) -> str:
    if tipo not in TIPOS_SINCRONIZACAO_MANUAL:
        raise TipoInvalidoError(f"tipo deve ser um de: {', '.join(TIPOS_SINCRONIZACAO_MANUAL)}")
    return tipo


def solicitar(db: Session, tipo: str, solicitado_por: str | None) -> SolicitacaoSincronizacao:
    _validar_tipo(tipo)
    db.execute(
        insert(SolicitacaoSincronizacao)
        .values(tipo=tipo, status="PENDENTE", solicitado_por=solicitado_por)
        .on_conflict_do_nothing(index_elements=["tipo"], index_where=text("status = 'PENDENTE'"))
    )
    db.flush()
    pendente = db.scalar(
        select(SolicitacaoSincronizacao).where(
            SolicitacaoSincronizacao.tipo == tipo, SolicitacaoSincronizacao.status == "PENDENTE"
        )
    )
    assert pendente is not None
    return pendente


def reivindicar_proximo(db: Session, agora: datetime) -> SolicitacaoSincronizacao | None:
    pedido = db.scalar(
        select(SolicitacaoSincronizacao)
        .where(SolicitacaoSincronizacao.status == "PENDENTE")
        .order_by(SolicitacaoSincronizacao.solicitado_em, SolicitacaoSincronizacao.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if pedido is None:
        return None
    pedido.status = "EM_EXECUCAO"
    pedido.iniciado_em = agora
    db.flush()
    return pedido


def concluir(db: Session, pedido_id: int, sincronizacao_id: int | None, agora: datetime) -> None:
    db.execute(
        update(SolicitacaoSincronizacao)
        .where(SolicitacaoSincronizacao.id == pedido_id)
        .values(status="CONCLUIDA", concluido_em=agora, sincronizacao_id=sincronizacao_id)
    )


def encerrar_orfas(db: Session, agora: datetime) -> int:
    execucoes = db.execute(
        update(Sincronizacao)
        .where(
            Sincronizacao.status == "em_andamento",
            Sincronizacao.tipo.in_(TIPOS_SINCRONIZACAO_MANUAL),
        )
        .values(status="erro", fim=agora, mensagem_erro="interrompida (worker reiniciado)")
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(SolicitacaoSincronizacao)
        .where(SolicitacaoSincronizacao.status == "EM_EXECUCAO")
        .values(status="CONCLUIDA", concluido_em=agora)
        .execution_options(synchronize_session=False)
    )
    return int(execucoes.rowcount or 0)  # type: ignore[attr-defined]


def ultima_execucao(db: Session, tipo: str) -> Sincronizacao | None:
    return db.scalar(
        select(Sincronizacao)
        .where(
            Sincronizacao.tipo == tipo,
            Sincronizacao.empresa_id.is_(None),
            Sincronizacao.sincronizacao_pai_id.is_(None),
        )
        .order_by(Sincronizacao.inicio.desc(), Sincronizacao.id.desc())
        .limit(1)
    )


def execucao_vencida(db: Session, tipo: str, intervalo_segundos: int, agora: datetime) -> bool:
    if intervalo_segundos <= 0:
        return False
    ultima = ultima_execucao(db, tipo)
    if ultima is None:
        return True
    return (agora - ultima.inicio).total_seconds() >= intervalo_segundos


def leitura_completa_vencida(
    db: Session, tipo: str, horario: str, tz: ZoneInfo, agora: datetime
) -> bool:
    if not horario:
        return False
    hora, minuto = (int(p) for p in horario.split(":"))
    local = agora.astimezone(tz)
    marco = datetime.combine(local.date(), time(hora, minuto), tzinfo=tz)
    if marco > local:
        marco -= timedelta(days=1)
    ultima = ultima_execucao(db, tipo)
    return ultima is None or ultima.inicio < marco


def execucoes_por_empresa(db: Session, pai_id: int) -> Sequence[Sincronizacao]:
    return db.scalars(
        select(Sincronizacao)
        .options(joinedload(Sincronizacao.empresa))
        .where(Sincronizacao.sincronizacao_pai_id == pai_id)
        .order_by(Sincronizacao.id)
    ).all()


@dataclass
class ResumoEstoque:
    linhas_ativas: int
    linhas_inativas: int
    produtos_consolidados: int
    consolidado_atualizado_em: datetime | None


@dataclass
class StatusSincronizacao:
    pendentes: Sequence[SolicitacaoSincronizacao]
    ultima_empresas: Sincronizacao | None
    ultima_estoque: Sincronizacao | None
    ultima_estoque_completo: Sincronizacao | None
    estoque_por_empresa: Sequence[Sincronizacao]
    erros_recentes: Sequence[IntegracaoErro]
    estoque: ResumoEstoque
    em_execucao: Sequence[SolicitacaoSincronizacao] = field(default_factory=list)
    ultima_precos: Sincronizacao | None = None
    ultima_precos_completo: Sincronizacao | None = None


def status(db: Session, limite_erros: int = 20) -> StatusSincronizacao:
    pedidos = db.scalars(
        select(SolicitacaoSincronizacao)
        .where(SolicitacaoSincronizacao.status.in_(("PENDENTE", "EM_EXECUCAO")))
        .order_by(SolicitacaoSincronizacao.solicitado_em)
    ).all()
    ultima_estoque = ultima_execucao(db, "estoque")
    ultima_completo = ultima_execucao(db, "estoque_completo")

    recente = max(
        (e for e in (ultima_estoque, ultima_completo) if e is not None),
        key=lambda e: (e.inicio, e.id),
        default=None,
    )

    ativas, inativas = db.execute(
        select(
            func.count().filter(EstoqueEmpresaLocalLote.ativo.is_(True)),
            func.count().filter(EstoqueEmpresaLocalLote.ativo.is_(False)),
        ).select_from(EstoqueEmpresaLocalLote)
    ).one()
    produtos, atualizado_em = db.execute(
        select(func.count(), func.max(EstoqueConsolidado.atualizado_em)).select_from(
            EstoqueConsolidado
        )
    ).one()

    return StatusSincronizacao(
        pendentes=[p for p in pedidos if p.status == "PENDENTE"],
        em_execucao=[p for p in pedidos if p.status == "EM_EXECUCAO"],
        ultima_empresas=ultima_execucao(db, "empresas"),
        ultima_estoque=ultima_estoque,
        ultima_estoque_completo=ultima_completo,
        ultima_precos=ultima_execucao(db, "precos"),
        ultima_precos_completo=ultima_execucao(db, "precos_completo"),
        estoque_por_empresa=execucoes_por_empresa(db, recente.id) if recente else [],
        erros_recentes=db.scalars(
            select(IntegracaoErro)
            .order_by(IntegracaoErro.ocorrido_em.desc(), IntegracaoErro.id.desc())
            .limit(limite_erros)
        ).all(),
        estoque=ResumoEstoque(ativas, inativas, produtos, atualizado_em),
    )
