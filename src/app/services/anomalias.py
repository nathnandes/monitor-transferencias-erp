from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased, joinedload

from app.anomalias.registros import RegistroTransferencia
from app.database.models import (
    AnomaliaExecucao,
    AnomaliaTransferencia,
    Empresa,
    Transferencia,
    TransferenciaItem,
    TransferenciaTratativa,
)
from app.dominio.transferencias import STATUS_PENDENTE, STATUS_PROCESSADA
from app.services.comum import condicao_entre_empresas
from app.services.controle_transferencias import Filtros, Tratativa, ultimas_tratativas

LIMITE_LISTA = 50
SITUACAO_RESOLVIDA = "RESOLVIDA"


@dataclass(frozen=True)
class ResultadoGravavel:
    transferencia_id: int
    score: float
    sinalizada: bool
    com_entrada: bool
    motivos: list[dict[str, Any]]


def _rotulo(empresa: Empresa) -> str:
    return f"{empresa.codigo} - {empresa.nome}"


def _condicoes_avaliaveis() -> tuple[Any, ...]:
    return (
        condicao_entre_empresas(),
        Transferencia.status.in_([STATUS_PENDENTE, STATUS_PROCESSADA]),
        Transferencia.empresa_destino_id.is_not(None),
        Transferencia.valor_total.is_not(None),
        Transferencia.valor_total > 0,
        Transferencia.data_criacao.is_not(None),
    )


def _para_registros(
    db: Session, consulta: Select[Transferencia], tz: ZoneInfo
) -> list[RegistroTransferencia]:
    transferencias = list(
        db.scalars(
            consulta.options(
                joinedload(Transferencia.empresa_origem),
                joinedload(Transferencia.empresa_destino),
            )
        )
    )
    if not transferencias:
        return []
    ids = [t.id for t in transferencias]
    itens = {
        linha.transferencia_id: linha
        for linha in db.execute(
            select(
                TransferenciaItem.transferencia_id,
                func.count().label("linhas"),
                func.coalesce(func.sum(TransferenciaItem.quantidade_solicitada), 0).label(
                    "enviada"
                ),
                func.coalesce(func.sum(TransferenciaItem.quantidade_processada), 0).label(
                    "recebida"
                ),
            )
            .where(TransferenciaItem.transferencia_id.in_(ids))
            .group_by(TransferenciaItem.transferencia_id)
        )
    }
    registros = []
    for t in transferencias:
        assert t.data_criacao is not None and t.valor_total is not None
        assert t.empresa_destino is not None
        linha = itens.get(t.id)
        com_entrada = t.data_processamento is not None
        registros.append(
            RegistroTransferencia(
                id=str(t.id),
                origem=_rotulo(t.empresa_origem),
                destino=_rotulo(t.empresa_destino),
                valor=float(t.valor_total),
                emitida_em=t.data_criacao.astimezone(tz),
                recebida_em=t.data_processamento.astimezone(tz)
                if t.data_processamento is not None
                else None,
                quantidade_itens=t.quantidade_itens or (linha.linhas if linha else 0),
                quantidade_enviada=float(linha.enviada) if linha else 0.0,
                quantidade_recebida=(float(linha.recebida) if linha else 0.0)
                if com_entrada
                else None,
            )
        )
    return registros


def carregar_treino(
    db: Session, *, inicio: datetime, fim: datetime, tz: ZoneInfo
) -> list[RegistroTransferencia]:
    return _para_registros(
        db,
        select(Transferencia)
        .where(
            *_condicoes_avaliaveis(),
            Transferencia.data_criacao >= inicio,
            Transferencia.data_criacao < fim,
        )
        .order_by(Transferencia.data_criacao, Transferencia.id),
        tz,
    )


def carregar_para_avaliar(
    db: Session, *, inicio: datetime, tz: ZoneInfo
) -> list[RegistroTransferencia]:
    return _para_registros(
        db,
        select(Transferencia)
        .outerjoin(
            AnomaliaTransferencia, AnomaliaTransferencia.transferencia_id == Transferencia.id
        )
        .where(
            *_condicoes_avaliaveis(),
            Transferencia.data_criacao >= inicio,
            or_(
                AnomaliaTransferencia.transferencia_id.is_(None),
                and_(
                    AnomaliaTransferencia.com_entrada.is_(False),
                    Transferencia.data_processamento.is_not(None),
                ),
            ),
        )
        .order_by(Transferencia.data_criacao, Transferencia.id),
        tz,
    )


def registrar_execucao(
    db: Session,
    *,
    agora: datetime,
    status: str,
    versao_modelo: str,
    notas_treino: int = 0,
    notas_avaliadas: int = 0,
    notas_sinalizadas: int = 0,
    limiar: float | None = None,
    mensagem: str | None = None,
) -> AnomaliaExecucao:
    execucao = AnomaliaExecucao(
        concluida_em=agora,
        status=status,
        versao_modelo=versao_modelo,
        notas_treino=notas_treino,
        notas_avaliadas=notas_avaliadas,
        notas_sinalizadas=notas_sinalizadas,
        limiar=limiar,
        mensagem=mensagem,
    )
    db.add(execucao)
    db.flush()
    return execucao


def gravar_resultados(
    db: Session,
    execucao: AnomaliaExecucao,
    resultados: Iterable[ResultadoGravavel],
    *,
    limiar: float,
    agora: datetime,
) -> None:
    linhas = [
        {
            "transferencia_id": r.transferencia_id,
            "execucao_id": execucao.id,
            "score": r.score,
            "limiar": limiar,
            "sinalizada": r.sinalizada,
            "com_entrada": r.com_entrada,
            "motivos": r.motivos,
            "avaliada_em": agora,
        }
        for r in resultados
    ]
    if not linhas:
        return
    comando = insert(AnomaliaTransferencia).values(linhas)
    colunas_novas = {
        nome: comando.excluded[nome]
        for nome in (
            "execucao_id",
            "score",
            "limiar",
            "sinalizada",
            "com_entrada",
            "motivos",
            "avaliada_em",
        )
    }
    db.execute(
        comando.on_conflict_do_update(
            index_elements=["transferencia_id"],
            set_={**colunas_novas, "updated_at": func.now()},
        )
    )
    db.expire_all()


def ultima_execucao(db: Session) -> AnomaliaExecucao | None:
    return db.scalar(
        select(AnomaliaExecucao)
        .order_by(AnomaliaExecucao.concluida_em.desc(), AnomaliaExecucao.id.desc())
        .limit(1)
    )


def execucao_vencida(db: Session, intervalo_segundos: int, agora: datetime) -> bool:
    ultima = ultima_execucao(db)
    if ultima is None:
        return True
    return (agora - ultima.concluida_em) >= timedelta(seconds=intervalo_segundos)


def _sem_tratativa_resolvida() -> Any:
    outra = aliased(TransferenciaTratativa)
    ultima = (
        select(func.max(outra.id))
        .where(outra.transferencia_id == Transferencia.id)
        .correlate(Transferencia)
        .scalar_subquery()
    )
    resolvida = (
        select(TransferenciaTratativa.id)
        .where(
            TransferenciaTratativa.id == ultima,
            TransferenciaTratativa.situacao == SITUACAO_RESOLVIDA,
        )
        .correlate(Transferencia)
        .exists()
    )
    return ~resolvida


def para_alerta(db: Session, desde: datetime) -> list[AnomaliaTransferencia]:
    return list(
        db.scalars(
            select(AnomaliaTransferencia)
            .join(AnomaliaTransferencia.transferencia)
            .options(
                joinedload(AnomaliaTransferencia.transferencia).options(
                    joinedload(Transferencia.empresa_origem),
                    joinedload(Transferencia.empresa_destino),
                )
            )
            .where(
                AnomaliaTransferencia.sinalizada.is_(True),
                *_condicoes_avaliaveis(),
                Transferencia.data_criacao >= desde,
                _sem_tratativa_resolvida(),
            )
            .order_by(desc(AnomaliaTransferencia.score), Transferencia.id)
        ).unique()
    )


@dataclass(frozen=True)
class PainelAnomalias:
    execucao: AnomaliaExecucao | None
    analisadas: int
    sinalizadas: int
    lista: list[AnomaliaTransferencia]
    tratativas: dict[int, Tratativa]


def _condicoes_filtro(filtros: Filtros, tz: ZoneInfo) -> list[Any]:
    condicoes: list[Any] = [condicao_entre_empresas()]
    if filtros.data_inicial:
        condicoes.append(
            Transferencia.data_criacao >= datetime.combine(filtros.data_inicial, time.min, tz)
        )
    if filtros.data_final:
        condicoes.append(
            Transferencia.data_criacao
            < datetime.combine(filtros.data_final + timedelta(days=1), time.min, tz)
        )
    if filtros.empresa:
        origem, destino = aliased(Empresa), aliased(Empresa)
        condicoes.append(
            or_(
                select(origem.id)
                .where(
                    origem.id == Transferencia.empresa_origem_id,
                    origem.codigo == filtros.empresa,
                )
                .exists(),
                select(destino.id)
                .where(
                    destino.id == Transferencia.empresa_destino_id,
                    destino.codigo == filtros.empresa,
                )
                .exists(),
            )
        )
    return condicoes


def painel(db: Session, filtros: Filtros, tz: ZoneInfo) -> PainelAnomalias:
    condicoes: Sequence[Any] = _condicoes_filtro(filtros, tz)
    contagem = db.execute(
        select(
            func.count().label("analisadas"),
            func.count().filter(AnomaliaTransferencia.sinalizada).label("sinalizadas"),
        )
        .select_from(AnomaliaTransferencia)
        .join(AnomaliaTransferencia.transferencia)
        .where(*condicoes)
    ).one()
    lista = list(
        db.scalars(
            select(AnomaliaTransferencia)
            .join(AnomaliaTransferencia.transferencia)
            .options(
                joinedload(AnomaliaTransferencia.transferencia).options(
                    joinedload(Transferencia.empresa_origem),
                    joinedload(Transferencia.empresa_destino),
                )
            )
            .where(AnomaliaTransferencia.sinalizada.is_(True), *condicoes)
            .order_by(desc(AnomaliaTransferencia.score), Transferencia.id)
            .limit(LIMITE_LISTA)
        ).unique()
    )
    return PainelAnomalias(
        execucao=ultima_execucao(db),
        analisadas=contagem.analisadas,
        sinalizadas=contagem.sinalizadas,
        lista=lista,
        tratativas=ultimas_tratativas(db, (a.transferencia_id for a in lista)),
    )
