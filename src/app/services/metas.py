from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import (
    NIVEIS_META,
    PERIODOS_META,
    Empresa,
    MetaAviso,
    MetaVenda,
    ParametrosMetas,
    Usuario,
    Venda,
    Vendedor,
)
from app.services import atividades

logger = get_logger(__name__)

MARCOS_PADRAO = [100]
_MESES = (
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro"
).split()


class MetaInvalida(ValueError):
    pass


def periodo_de(dia: date, periodo: str) -> tuple[date, date]:
    if periodo == "DIA":
        return dia, dia
    if periodo == "SEMANA":
        inicio = dia - timedelta(days=dia.weekday())
        return inicio, inicio + timedelta(days=6)
    inicio = dia.replace(day=1)
    proximo = (inicio + timedelta(days=32)).replace(day=1)
    return inicio, proximo - timedelta(days=1)


def rotulo_periodo(periodo: str, inicio: date) -> str:
    if periodo == "DIA":
        return f"{inicio:%d/%m/%Y}"
    if periodo == "SEMANA":
        return f"semana de {inicio:%d/%m} a {inicio + timedelta(days=6):%d/%m}"
    return f"{_MESES[inicio.month - 1]}/{inicio.year}"


def _do_periodo(periodo: str, inicio: date) -> str:
    if periodo == "DIA":
        return f"do dia {inicio:%d/%m}"
    if periodo == "SEMANA":
        return "da semana"
    return "do mês"


def moeda(valor: Decimal) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


@dataclass
class MetaComAlvo:
    meta: MetaVenda
    alvo: str


def _nomes(db: Session, metas: list[MetaVenda]) -> dict[int, str]:
    ids_vendedores = {m.id_vendedor for m in metas if m.id_vendedor}
    vendedores = dict(
        db.execute(
            select(Vendedor.id_erp, Vendedor.nome).where(Vendedor.id_erp.in_(ids_vendedores))
        ).all()
    )
    nomes = {}
    for m in metas:
        if m.nivel == "GRUPO":
            nomes[m.id] = "Grupo (todas as lojas)"
        elif m.nivel == "EMPRESA":
            assert m.empresa is not None
            nomes[m.id] = m.empresa.nome
        else:
            nomes[m.id] = vendedores.get(m.id_vendedor or "") or f"Vendedor {m.id_vendedor}"
    return nomes


def listar(db: Session) -> list[MetaComAlvo]:
    metas = list(
        db.scalars(
            select(MetaVenda).order_by(
                MetaVenda.nivel, MetaVenda.periodo, MetaVenda.referencia.nulls_first(), MetaVenda.id
            )
        )
    )
    nomes = _nomes(db, metas)
    return [MetaComAlvo(m, nomes[m.id]) for m in metas]


def salvar(
    db: Session,
    *,
    nivel: str,
    periodo: str,
    valor: Decimal,
    usuario: Usuario,
    empresa_id: int | None = None,
    id_vendedor: str | None = None,
    referencia: date | None = None,
) -> MetaVenda:
    if nivel not in NIVEIS_META or periodo not in PERIODOS_META:
        raise MetaInvalida("Nível ou período desconhecido.")
    if valor <= 0:
        raise MetaInvalida("A meta precisa ser maior que zero.")
    if nivel == "GRUPO":
        empresa_id, id_vendedor = None, None
    elif nivel == "EMPRESA":
        id_vendedor = None
        if empresa_id is None or db.get(Empresa, empresa_id) is None:
            raise MetaInvalida("Escolha a loja da meta.")
    else:
        empresa_id = None
        id_vendedor = (id_vendedor or "").strip() or None
        if id_vendedor is None:
            raise MetaInvalida("Escolha o vendedor da meta.")
    if referencia is not None:
        referencia = periodo_de(referencia, periodo)[0]

    meta = db.scalar(
        select(MetaVenda).where(
            MetaVenda.nivel == nivel,
            MetaVenda.periodo == periodo,
            MetaVenda.empresa_id.is_(None)
            if empresa_id is None
            else MetaVenda.empresa_id == empresa_id,
            MetaVenda.id_vendedor.is_(None)
            if id_vendedor is None
            else MetaVenda.id_vendedor == id_vendedor,
            MetaVenda.referencia.is_(None)
            if referencia is None
            else MetaVenda.referencia == referencia,
        )
    )
    if meta is None:
        meta = MetaVenda(
            nivel=nivel,
            empresa_id=empresa_id,
            id_vendedor=id_vendedor,
            periodo=periodo,
            referencia=referencia,
        )
        db.add(meta)
    meta.valor = valor.quantize(Decimal("0.01"))
    meta.usuario_id = usuario.id
    meta.usuario_nome = usuario.nome_exibicao
    meta.updated_at = func.now()
    db.flush()
    db.refresh(meta)
    return meta


def excluir(db: Session, meta_id: int) -> MetaVenda:
    meta = db.get(MetaVenda, meta_id)
    if meta is None:
        raise LookupError(meta_id)
    db.delete(meta)
    db.flush()
    return meta


def marcos(db: Session) -> list[int]:
    linha = db.get(ParametrosMetas, 1)
    return sorted(linha.marcos) if linha else list(MARCOS_PADRAO)


def definir_marcos(db: Session, novos: list[int], usuario: Usuario) -> list[int]:
    unicos = sorted(set(novos))
    if not 1 <= len(unicos) <= 10 or any(not 0 < m <= 1000 for m in unicos):
        raise MetaInvalida("Informe de 1 a 10 marcos, cada um entre 1% e 1000%.")
    linha = db.get(ParametrosMetas, 1) or ParametrosMetas(id=1)
    linha.marcos = unicos
    linha.usuario_id = usuario.id
    linha.usuario_nome = usuario.nome_exibicao
    linha.updated_at = func.now()
    db.add(linha)
    db.flush()
    return unicos


@dataclass
class Progresso:
    meta: MetaVenda
    alvo: str
    inicio: date
    fim: date
    realizado: Decimal

    @property
    def percentual(self) -> Decimal:
        return (self.realizado * 100 / self.meta.valor).quantize(Decimal("0.1"), ROUND_HALF_UP)

    @property
    def falta(self) -> Decimal:
        return max(self.meta.valor - self.realizado, Decimal(0))


def _vigentes(db: Session, dia: date) -> list[tuple[MetaVenda, date, date]]:
    inicios = {p: periodo_de(dia, p)[0] for p in PERIODOS_META}
    candidatas = db.scalars(
        select(MetaVenda).where(
            or_(
                MetaVenda.referencia.is_(None),
                *(
                    (MetaVenda.periodo == p) & (MetaVenda.referencia == inicio)
                    for p, inicio in inicios.items()
                ),
            )
        )
    ).all()
    escolhidas: dict[tuple[str, int | None, str | None, str], MetaVenda] = {}
    for m in candidatas:
        chave = (m.nivel, m.empresa_id, m.id_vendedor, m.periodo)
        atual = escolhidas.get(chave)
        if atual is None or (atual.referencia is None and m.referencia is not None):
            escolhidas[chave] = m
    return [(m, *periodo_de(dia, m.periodo)) for m in escolhidas.values()]


def _vendido(db: Session, inicio: date, fim: date) -> dict[tuple[str, object], Decimal]:
    totais: dict[tuple[str, object], Decimal] = defaultdict(Decimal)
    linhas = db.execute(
        select(Venda.empresa_id, Venda.id_vendedor, func.sum(Venda.valor_total))
        .where(Venda.cancelada.is_(False), Venda.data_venda.between(inicio, fim))
        .group_by(Venda.empresa_id, Venda.id_vendedor)
    )
    for empresa_id, id_vendedor, soma in linhas:
        valor = Decimal(str(soma or 0))
        totais[("GRUPO", None)] += valor
        totais[("EMPRESA", empresa_id)] += valor
        if id_vendedor is not None:
            totais[("VENDEDOR", id_vendedor)] += valor
    return totais


def progresso(db: Session, dia: date) -> list[Progresso]:
    vigentes = _vigentes(db, dia)
    nomes = _nomes(db, [m for m, *_ in vigentes])
    vendidos: dict[tuple[date, date], dict[tuple[str, object], Decimal]] = {}
    resultado = []
    for meta, inicio, fim in vigentes:
        if (inicio, fim) not in vendidos:
            vendidos[(inicio, fim)] = _vendido(db, inicio, fim)
        alvo: object = meta.empresa_id if meta.nivel == "EMPRESA" else meta.id_vendedor
        realizado = vendidos[(inicio, fim)].get((meta.nivel, alvo), Decimal(0))
        resultado.append(Progresso(meta, nomes[meta.id], inicio, fim, realizado))
    ordem = {n: i for i, n in enumerate(NIVEIS_META)}
    ordem_periodo = {p: i for i, p in enumerate(PERIODOS_META)}
    resultado.sort(key=lambda p: (ordem_periodo[p.meta.periodo], ordem[p.meta.nivel], p.alvo))
    return resultado


def avaliar_avisos(db: Session, agora: datetime, tz: ZoneInfo) -> int:
    dia = agora.astimezone(tz).date()
    lista_marcos = marcos(db)
    progressos = progresso(db, dia)
    if not progressos:
        return 0
    avisados = {
        (meta_id, inicio, marco)
        for meta_id, inicio, marco in db.execute(
            select(MetaAviso.meta_id, MetaAviso.periodo_inicio, MetaAviso.marco).where(
                MetaAviso.meta_id.in_([p.meta.id for p in progressos])
            )
        )
    }
    avisos = 0
    for p in progressos:
        novos = [
            m
            for m in lista_marcos
            if p.percentual >= m and (p.meta.id, p.inicio, m) not in avisados
        ]
        if not novos:
            continue
        db.execute(
            insert(MetaAviso)
            .values([{"meta_id": p.meta.id, "periodo_inicio": p.inicio, "marco": m} for m in novos])
            .on_conflict_do_nothing()
        )
        marco = max(novos)
        do_periodo = _do_periodo(p.meta.periodo, p.inicio)
        titulo = (
            f"{p.alvo} bateu a meta {do_periodo}"
            if marco >= 100
            else f"{p.alvo} chegou a {marco}% da meta {do_periodo}"
        )
        atividades.registrar(
            db,
            "meta_atingida",
            titulo,
            usuario_nome="Sistema",
            valores={
                "alvo": p.alvo,
                "periodo": rotulo_periodo(p.meta.periodo, p.inicio),
                "meta": moeda(p.meta.valor),
                "realizado": moeda(p.realizado),
                "percentual": f"{p.percentual:.0f}%",
                "falta": moeda(p.falta),
            },
            empresas=[p.meta.empresa_id] if p.meta.empresa_id else [],
            agora=agora,
        )
        avisos += 1
    if avisos:
        logger.info("metas: %d avisos", avisos)
    return avisos
