from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, false, func, or_, select, true
from sqlalchemy.orm import Session, joinedload

from app.database.models import SEVERIDADES_EVENTO, Empresa, Evento, Sincronizacao, Transferencia
from app.dominio.intervalo import Intervalo, IntervaloInvalido
from app.dominio.transferencias import (
    LIMITES_PADRAO,
    STATUS_ERRO,
    STATUS_PENDENTE,
    STATUS_PROCESSADA,
    Limites,
)
from app.services import limites_pendencia
from app.services.comum import condicao_entre_empresas

NivelStatus = Literal["ok", "atencao", "critico"]


@dataclass(frozen=True)
class ContagemEmpresa:
    pendentes: int = 0
    pendentes_atrasadas: int = 0
    pendentes_criticas: int = 0
    com_erro: int = 0


@dataclass(frozen=True)
class StatusEmpresa:
    empresa: Empresa
    status: NivelStatus
    motivos: list[str]
    ultima_sincronizacao: Sincronizacao | None
    contagem: ContagemEmpresa


@dataclass(frozen=True)
class FiltroResumo:
    empresa: Empresa | None = None
    periodo: Intervalo | None = None
    comparacao: Intervalo | None = None

    def __post_init__(self) -> None:
        if self.comparacao and not self.periodo:
            raise IntervaloInvalido("A comparação exige um período.")


@dataclass(frozen=True)
class Fluxo:
    criadas: int
    processadas: int
    eventos: int


@dataclass(frozen=True)
class SituacaoAtual:
    pendentes: int
    pendentes_atrasadas: int
    com_erro: int


@dataclass(frozen=True)
class ResumoDashboard:
    gerado_em: datetime
    total: int
    processadas: int
    pendentes: int
    com_erro: int
    empresas_ativas: int
    ultima_sincronizacao: Sincronizacao | None
    eventos_por_severidade: dict[str, int]
    status_por_empresa: list[StatusEmpresa] = field(default_factory=list)
    filtro: FiltroResumo = field(default_factory=FiltroResumo)
    periodo: Fluxo | None = None
    comparacao: Fluxo | None = None
    situacao_atual: SituacaoAtual = field(default_factory=lambda: SituacaoAtual(0, 0, 0))
    limites: Limites = LIMITES_PADRAO


def classificar_empresa(
    status_ultima_sincronizacao: str | None,
    contagem: ContagemEmpresa,
    limites: Limites = LIMITES_PADRAO,
) -> tuple[NivelStatus, list[str]]:
    criticos: list[str] = []
    atencao: list[str] = []

    if status_ultima_sincronizacao is None:
        atencao.append("Nenhuma sincronização registrada.")
    elif status_ultima_sincronizacao == "erro":
        criticos.append("Última sincronização terminou com erro.")
    elif status_ultima_sincronizacao == "parcial":
        atencao.append("Última sincronização foi parcial.")

    if contagem.com_erro:
        criticos.append(f"{contagem.com_erro} transferência(s) com status ERRO.")
    if contagem.pendentes_criticas:
        criticos.append(
            f"{contagem.pendentes_criticas} transferência(s) pendente(s) "
            f"há mais de {limites.horas_critico}h."
        )
    if contagem.pendentes_atrasadas:
        atencao.append(
            f"{contagem.pendentes_atrasadas} transferência(s) pendente(s) "
            f"há mais de {limites.horas_atencao}h."
        )

    if criticos:
        return "critico", criticos + atencao
    if atencao:
        return "atencao", atencao
    return "ok", []


def _contagens_por_origem(
    db: Session, agora: datetime, limites: Limites
) -> dict[int, ContagemEmpresa]:
    status = Transferencia.status
    pendente = status == STATUS_PENDENTE
    limite_atraso = agora - limites.atencao
    limite_critico = agora - limites.critico
    linhas = db.execute(
        select(
            Transferencia.empresa_origem_id,
            func.count().filter(pendente),
            func.count().filter(
                pendente,
                Transferencia.data_criacao < limite_atraso,
                Transferencia.data_criacao >= limite_critico,
            ),
            func.count().filter(pendente, Transferencia.data_criacao < limite_critico),
            func.count().filter(status == STATUS_ERRO),
        )
        .where(condicao_entre_empresas())
        .group_by(Transferencia.empresa_origem_id)
    ).all()
    return {empresa_id: ContagemEmpresa(*contagens) for empresa_id, *contagens in linhas}


def _ultima_sincronizacao_por_empresa(db: Session) -> dict[int, Sincronizacao]:

    ordem = (
        func.row_number()
        .over(
            partition_by=Sincronizacao.empresa_id,
            order_by=(Sincronizacao.inicio.desc(), Sincronizacao.id.desc()),
        )
        .label("ordem")
    )
    recentes = (
        select(Sincronizacao.id, ordem).where(Sincronizacao.empresa_id.is_not(None)).subquery()
    )
    sincronizacoes = db.scalars(
        select(Sincronizacao)
        .join(recentes, recentes.c.id == Sincronizacao.id)
        .where(recentes.c.ordem == 1)
    ).all()
    return {s.empresa_id: s for s in sincronizacoes if s.empresa_id is not None}


def resumo_dashboard(
    db: Session,
    agora: datetime | None = None,
    filtro: FiltroResumo | None = None,
    tz: ZoneInfo | None = None,
) -> ResumoDashboard:
    agora = agora or datetime.now(UTC)
    filtro = filtro or FiltroResumo()
    tz = tz or ZoneInfo("UTC")
    empresa = filtro.empresa
    periodo, comparacao = filtro.periodo, filtro.comparacao

    def dentro(
        intervalo: Intervalo | None, coluna: Any, sem_intervalo: Callable[[], Any]
    ) -> ColumnElement[bool]:
        return intervalo.condicao(coluna, tz) if intervalo else sem_intervalo()

    limites = limites_pendencia.limites(db)
    status = Transferencia.status
    pendente = status == STATUS_PENDENTE
    criada_no_periodo = dentro(periodo, Transferencia.data_criacao, true)

    consulta = select(
        func.count().filter(criada_no_periodo),
        func.count().filter(criada_no_periodo, status == STATUS_PROCESSADA),
        func.count().filter(criada_no_periodo, pendente),
        func.count().filter(criada_no_periodo, status == STATUS_ERRO),
        func.count().filter(dentro(periodo, Transferencia.data_processamento, true)),
        func.count().filter(dentro(comparacao, Transferencia.data_criacao, false)),
        func.count().filter(dentro(comparacao, Transferencia.data_processamento, false)),
        func.count().filter(pendente),
        func.count().filter(pendente, Transferencia.data_criacao < agora - limites.atencao),
        func.count().filter(status == STATUS_ERRO),
    ).where(condicao_entre_empresas())
    if empresa:
        consulta = consulta.where(
            or_(
                Transferencia.empresa_origem_id == empresa.id,
                Transferencia.empresa_destino_id == empresa.id,
            )
        )
    (
        total,
        processadas,
        pendentes,
        com_erro,
        processadas_no_periodo,
        criadas_na_comparacao,
        processadas_na_comparacao,
        pendentes_agora,
        atrasadas_agora,
        com_erro_agora,
    ) = db.execute(consulta).one()

    ultima = select(Sincronizacao).options(joinedload(Sincronizacao.empresa))
    if empresa:
        ultima = ultima.where(Sincronizacao.empresa_id == empresa.id)
    ultima_global = db.scalar(
        ultima.order_by(Sincronizacao.inicio.desc(), Sincronizacao.id.desc()).limit(1)
    )

    consulta_eventos = select(
        Evento.severidade,
        func.count().filter(dentro(periodo, Evento.data_evento, true)),
        func.count().filter(dentro(comparacao, Evento.data_evento, false)),
    ).group_by(Evento.severidade)
    if empresa:
        consulta_eventos = consulta_eventos.where(Evento.empresa_id == empresa.id)
    eventos = dict.fromkeys(SEVERIDADES_EVENTO, 0)
    eventos_na_comparacao = 0
    for severidade, no_periodo, na_comparacao in db.execute(consulta_eventos).all():
        eventos[severidade] = no_periodo
        eventos_na_comparacao += na_comparacao

    consulta_ativas = select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.codigo)
    if empresa:
        consulta_ativas = consulta_ativas.where(Empresa.id == empresa.id)
    ativas = db.scalars(consulta_ativas).all()
    contagens = _contagens_por_origem(db, agora, limites)
    sincronizacoes = _ultima_sincronizacao_por_empresa(db)

    status_por_empresa = []
    for ativa in ativas:
        contagem = contagens.get(ativa.id, ContagemEmpresa())
        sincronizacao = sincronizacoes.get(ativa.id)
        nivel, motivos = classificar_empresa(
            sincronizacao.status if sincronizacao else None, contagem, limites
        )
        status_por_empresa.append(StatusEmpresa(ativa, nivel, motivos, sincronizacao, contagem))

    return ResumoDashboard(
        gerado_em=agora,
        total=total,
        processadas=processadas,
        pendentes=pendentes,
        com_erro=com_erro,
        empresas_ativas=len(ativas),
        ultima_sincronizacao=ultima_global,
        eventos_por_severidade=eventos,
        status_por_empresa=status_por_empresa,
        filtro=filtro,
        periodo=(Fluxo(total, processadas_no_periodo, sum(eventos.values())) if periodo else None),
        comparacao=(
            Fluxo(criadas_na_comparacao, processadas_na_comparacao, eventos_na_comparacao)
            if comparacao
            else None
        ),
        situacao_atual=SituacaoAtual(pendentes_agora, atrasadas_agora, com_erro_agora),
        limites=limites,
    )
