from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database.models import Empresa, Transferencia
from app.dominio.coi import COIS_FISCAIS
from app.dominio.intervalo import Intervalo
from app.dominio.transferencias import STATUS_CANCELADA, STATUS_PENDENTE, STATUS_PROCESSADA
from app.services.comum import condicao_entre_empresas

Granularidade = Literal["hora", "dia", "mes"]

LIMITE_DIARIO = 62
HISTORICO_MAXIMO = timedelta(days=730)


@dataclass
class Ponto:
    chave: str

    a_receber: int = 0
    recebidas: int = 0

    enviadas: int = 0
    itens_enviados: int = 0
    aguardando_destino: int = 0

    coi_errado: int = 0

    para_empresa: int = 0
    para_empresa_com_entrada: int = 0
    recebidas_com_criacao: int = 0
    soma_horas_entrada: float = 0.0

    @property
    def taxa_entrada(self) -> float | None:
        if not self.para_empresa:
            return None
        return round(self.para_empresa_com_entrada * 100 / self.para_empresa, 1)

    @property
    def tempo_medio_entrada_horas(self) -> float | None:
        if not self.recebidas_com_criacao:
            return None
        return round(self.soma_horas_entrada / self.recebidas_com_criacao, 1)

    def somar(self, outro: "Ponto") -> None:
        for nome in (
            "a_receber",
            "recebidas",
            "enviadas",
            "itens_enviados",
            "aguardando_destino",
            "coi_errado",
            "para_empresa",
            "para_empresa_com_entrada",
            "recebidas_com_criacao",
            "soma_horas_entrada",
        ):
            setattr(self, nome, getattr(self, nome) + getattr(outro, nome))


@dataclass(frozen=True)
class IndicadoresEmpresa:
    empresa: Empresa
    totais: Ponto
    serie: list[Ponto]


@dataclass(frozen=True)
class IndicadoresPorEmpresa:
    gerado_em: datetime
    granularidade: Granularidade
    inicio: date
    fim: date
    empresas: list[IndicadoresEmpresa] = field(default_factory=list)


def granularidade_do_intervalo(intervalo: Intervalo) -> Granularidade:
    dias = (intervalo.fim - intervalo.inicio).days + 1
    if dias == 1:
        return "hora"
    if dias <= LIMITE_DIARIO:
        return "dia"
    return "mes"


def chaves_dos_baldes(intervalo: Intervalo, granularidade: Granularidade) -> list[str]:
    if granularidade == "hora":
        return [f"{intervalo.inicio.isoformat()}T{h:02d}" for h in range(24)]
    if granularidade == "dia":
        dias = (intervalo.fim - intervalo.inicio).days + 1
        return [(intervalo.inicio + timedelta(days=d)).isoformat() for d in range(dias)]
    chaves = []
    ano, mes = intervalo.inicio.year, intervalo.inicio.month
    while (ano, mes) <= (intervalo.fim.year, intervalo.fim.month):
        chaves.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return chaves


def _chave(local: datetime, granularidade: Granularidade) -> str:
    if granularidade == "hora":
        return f"{local.date().isoformat()}T{local.hour:02d}"
    if granularidade == "dia":
        return local.date().isoformat()
    return f"{local.year:04d}-{local.month:02d}"


def _intervalo_sem_periodo(db: Session, agora: datetime, tz: ZoneInfo) -> Intervalo:
    hoje = agora.astimezone(tz).date()
    primeira = db.scalar(select(func.min(Transferencia.data_criacao)))
    if primeira is None:
        return Intervalo(hoje, hoje)
    inicio = max(primeira.astimezone(tz).date(), hoje - HISTORICO_MAXIMO)
    return Intervalo(min(inicio, hoje), hoje)


def indicadores_por_empresa(
    db: Session,
    *,
    periodo: Intervalo | None = None,
    empresa: Empresa | None = None,
    tz: ZoneInfo | None = None,
    agora: datetime | None = None,
) -> IndicadoresPorEmpresa:
    agora = agora or datetime.now(UTC)
    tz = tz or ZoneInfo("UTC")
    intervalo = periodo or _intervalo_sem_periodo(db, agora, tz)
    granularidade = granularidade_do_intervalo(intervalo)
    chaves = chaves_dos_baldes(intervalo, granularidade)

    consulta_ativas = select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.codigo)
    if empresa:
        consulta_ativas = consulta_ativas.where(Empresa.id == empresa.id)
    ativas = db.scalars(consulta_ativas).all()
    ids = [e.id for e in ativas]

    pontos: dict[int, dict[str, Ponto]] = defaultdict(dict)

    def ponto(empresa_id: int, local: datetime) -> Ponto:
        chave = _chave(local, granularidade)
        return pontos[empresa_id].setdefault(chave, Ponto(chave))

    def balde(coluna: Any) -> Any:
        return func.date_trunc(
            "month" if granularidade == "mes" else "day" if granularidade == "dia" else "hour",
            func.timezone(tz.key, coluna),
        )

    status = Transferencia.status
    pendente = status == STATUS_PENDENTE
    com_problema = func.jsonb_array_length(Transferencia.problemas_coi) > 0
    monitorada = (
        status != STATUS_CANCELADA,
        condicao_entre_empresas(),
        or_(
            Transferencia.coi.is_(None),
            Transferencia.coi.not_in([str(c) for c in COIS_FISCAIS]),
        ),
    )

    if ids:
        criacao = balde(Transferencia.data_criacao)
        por_origem = (
            select(
                Transferencia.empresa_origem_id,
                criacao,
                func.count(),
                func.coalesce(func.sum(Transferencia.quantidade_itens), 0),
                func.count().filter(pendente),
                func.count().filter(com_problema),
            )
            .where(
                *monitorada,
                Transferencia.empresa_origem_id.in_(ids),
                intervalo.condicao(Transferencia.data_criacao, tz),
            )
            .group_by(Transferencia.empresa_origem_id, criacao)
        )
        for empresa_id, local, enviadas, itens, aguardando, erradas in db.execute(por_origem):
            p = ponto(empresa_id, local)
            p.enviadas, p.itens_enviados = enviadas, int(itens)
            p.aguardando_destino, p.coi_errado = aguardando, erradas

        por_destino = (
            select(
                Transferencia.empresa_destino_id,
                criacao,
                func.count(),
                func.count().filter(status == STATUS_PROCESSADA),
                func.count().filter(pendente),
                func.count().filter(com_problema),
            )
            .where(
                *monitorada,
                Transferencia.empresa_destino_id.in_(ids),
                Transferencia.empresa_destino_id != Transferencia.empresa_origem_id,
                intervalo.condicao(Transferencia.data_criacao, tz),
            )
            .group_by(Transferencia.empresa_destino_id, criacao)
        )
        for empresa_id, local, para, com_entrada, a_receber, erradas in db.execute(por_destino):
            p = ponto(empresa_id, local)
            p.para_empresa, p.para_empresa_com_entrada = para, com_entrada
            p.a_receber = a_receber
            p.coi_errado += erradas

        entrada = balde(Transferencia.data_processamento)
        horas = (
            func.extract("epoch", Transferencia.data_processamento - Transferencia.data_criacao)
            / 3600
        )
        por_entrada = (
            select(
                Transferencia.empresa_destino_id,
                entrada,
                func.count(),
                func.count(Transferencia.data_criacao),
                func.coalesce(func.sum(horas), 0),
            )
            .where(
                *monitorada,
                status == STATUS_PROCESSADA,
                Transferencia.empresa_destino_id.in_(ids),
                intervalo.condicao(Transferencia.data_processamento, tz),
            )
            .group_by(Transferencia.empresa_destino_id, entrada)
        )
        for empresa_id, local, recebidas, com_criacao, soma_horas in db.execute(por_entrada):
            p = ponto(empresa_id, local)
            p.recebidas, p.recebidas_com_criacao = recebidas, com_criacao
            p.soma_horas_entrada = float(soma_horas)

    resultado = []
    for ativa in ativas:
        da_empresa = pontos.get(ativa.id, {})
        serie = [da_empresa.get(chave) or Ponto(chave) for chave in chaves]
        totais = Ponto("total")
        for p in serie:
            totais.somar(p)
        resultado.append(IndicadoresEmpresa(ativa, totais, serie))

    return IndicadoresPorEmpresa(
        gerado_em=agora,
        granularidade=granularidade,
        inicio=intervalo.inicio,
        fim=intervalo.fim,
        empresas=resultado,
    )
