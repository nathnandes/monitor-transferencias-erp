from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Integer, and_, any_, case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from app.database.models import (
    Empresa,
    PrazoRota,
    PrecoProdutoEmpresa,
    Produto,
    Transferencia,
    TransferenciaItem,
    TransferenciaTratativa,
)
from app.dominio.transferencias import STATUS_CANCELADA, STATUS_PENDENTE, STATUS_PROCESSADA
from app.services import limites_pendencia
from app.services.comum import condicao_entre_empresas

CFOPS_SAIDA = frozenset({"5151", "5152", "5408", "5409"})
CFOPS_ENTRADA = frozenset({"1151", "1152", "1408", "1409"})

LIMITE_LISTAS = 50


Ocorrencia = Literal["FORA_DO_PRAZO", "DIVERGENTE", "FISCAL", "SEM_TRATATIVA"]


class IntervaloDeDatasInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Filtros:
    empresa: str | None = None
    data_inicial: date | None = None
    data_final: date | None = None

    def __post_init__(self) -> None:
        if self.data_inicial and self.data_final and self.data_inicial > self.data_final:
            raise IntervaloDeDatasInvalido(
                f"data_inicial ({self.data_inicial}) é posterior a data_final ({self.data_final})."
            )


@dataclass(frozen=True)
class EmpresaRef:
    id: int
    codigo: str
    nome: str


@dataclass(frozen=True)
class Tratativa:
    situacao: str
    usuario_nome: str
    observacao: str
    created_at: datetime


@dataclass
class TransferenciaRef:
    id: int
    numero_nota: str | None
    origem: EmpresaRef
    destino: EmpresaRef | None
    status: str | None
    data_criacao: datetime | None
    valor_total: Decimal | None
    usuario_emissao: str | None
    tratativa: Tratativa | None = None


@dataclass
class TransitoDestino:
    empresa: EmpresaRef | None
    quantidade: int = 0
    valor: Decimal = Decimal(0)
    mais_antiga: datetime | None = None


@dataclass
class Rota:
    origem: EmpresaRef
    destino: EmpresaRef
    prazo_horas: int
    prazo_padrao: bool
    enviadas: int = 0
    recebidas: int = 0
    pendentes: int = 0
    fora_do_prazo: int = 0
    divergentes: int = 0
    valor_enviado: Decimal = Decimal(0)
    tempo_medio_horas: float | None = None
    _horas: list[float] = field(default_factory=list, repr=False)


@dataclass(frozen=True)
class ItemDivergente:
    id_produto: str
    descricao: str | None
    enviada: Decimal
    recebida: Decimal
    diferenca: Decimal
    valor_diferenca: Decimal | None
    sem_saida: bool = False


@dataclass
class Divergencia:
    transferencia: TransferenciaRef
    itens: list[ItemDivergente]
    valor_diferenca: Decimal


@dataclass(frozen=True)
class ProblemaFiscal:
    transferencia: TransferenciaRef
    tipo: str
    detalhe: str


@dataclass
class Emissor:
    usuario: str
    enviadas: int = 0
    fora_do_prazo: int = 0
    divergentes: int = 0
    problemas_fiscais: int = 0


@dataclass
class Resumo:
    em_transito_quantidade: int
    em_transito_valor: Decimal
    fora_do_prazo: int
    divergentes: int
    valor_divergencia: Decimal
    problemas_fiscais: int
    sem_tratativa: int


@dataclass
class PainelControle:
    resumo: Resumo
    em_transito: list[TransitoDestino]
    rotas: list[Rota]
    divergencias: list[Divergencia]
    fiscal: list[ProblemaFiscal]
    emissores: list[Emissor]
    prazo_padrao_horas: int
    cfops_saida: list[str] = field(default_factory=lambda: sorted(CFOPS_SAIDA))
    cfops_entrada: list[str] = field(default_factory=lambda: sorted(CFOPS_ENTRADA))


def prazo_padrao_horas(db: Session) -> int:
    return limites_pendencia.limites(db).horas_atencao


def prazos_por_rota(db: Session) -> dict[tuple[int, int], int]:
    return {
        (p.empresa_origem_id, p.empresa_destino_id): p.horas for p in db.scalars(select(PrazoRota))
    }


def definir_prazos(
    db: Session, prazos: Iterable[tuple[str, str, int | None]], usuario: str
) -> None:
    por_codigo = {e.codigo: e.id for e in db.scalars(select(Empresa))}
    atuais = {(p.empresa_origem_id, p.empresa_destino_id): p for p in db.scalars(select(PrazoRota))}
    for origem, destino, horas in prazos:
        if origem not in por_codigo or destino not in por_codigo:
            raise ValueError(f"Empresa desconhecida na rota {origem} → {destino}.")
        if origem == destino:
            raise ValueError("Origem e destino iguais.")
        if horas is not None and not 0 < horas <= 720:
            raise ValueError("Prazo deve ficar entre 1 e 720 horas.")
        chave = (por_codigo[origem], por_codigo[destino])
        atual = atuais.get(chave)
        if horas is None:
            if atual is not None:
                db.delete(atual)
        elif atual is None:
            db.add(
                PrazoRota(
                    empresa_origem_id=chave[0],
                    empresa_destino_id=chave[1],
                    horas=horas,
                    atualizado_por=usuario,
                )
            )
        else:
            atual.horas = horas
            atual.atualizado_por = usuario


def registrar_tratativa(
    db: Session,
    transferencia_id: int,
    *,
    usuario_id: int,
    usuario_nome: str,
    situacao: str,
    observacao: str,
) -> TransferenciaTratativa | None:
    if db.get(Transferencia, transferencia_id) is None:
        return None
    tratativa = TransferenciaTratativa(
        transferencia_id=transferencia_id,
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
        situacao=situacao,
        observacao=observacao.strip(),
    )
    db.add(tratativa)
    db.flush()
    db.refresh(tratativa)
    return tratativa


def listar_tratativas(db: Session, transferencia_id: int) -> list[TransferenciaTratativa]:
    return list(
        db.scalars(
            select(TransferenciaTratativa)
            .where(TransferenciaTratativa.transferencia_id == transferencia_id)
            .order_by(TransferenciaTratativa.id.desc())
        )
    )


def _algum_de(coluna: InstrumentedAttribute[int], ids: list[int]) -> ColumnElement[bool]:
    return coluna == any_(literal(ids, ARRAY(Integer)))


def ultimas_tratativas(db: Session, ids: Iterable[int]) -> dict[int, Tratativa]:
    ids = list(set(ids))
    if not ids:
        return {}
    ultimas = (
        select(func.max(TransferenciaTratativa.id))
        .where(_algum_de(TransferenciaTratativa.transferencia_id, ids))
        .group_by(TransferenciaTratativa.transferencia_id)
    )
    linhas = db.scalars(
        select(TransferenciaTratativa).where(TransferenciaTratativa.id.in_(ultimas))
    )
    return {
        t.transferencia_id: Tratativa(t.situacao, t.usuario_nome, t.observacao, t.created_at)
        for t in linhas
    }


def _inicio_do_dia(dia: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(dia, time.min, tzinfo=tz)


def _horas(inicio: datetime, fim: datetime) -> float:
    return (fim - inicio).total_seconds() / 3600


def _decimal(valor: Any) -> Decimal:
    try:
        return Decimal(str(valor))
    except Exception:
        return Decimal(0)


def painel_controle(
    db: Session, filtros: Filtros, *, tz: ZoneInfo, agora: datetime
) -> PainelControle:
    return _calcular(db, filtros, tz=tz, agora=agora)[0]


def ids_com_ocorrencia(
    db: Session, filtros: Filtros, ocorrencia: Ocorrencia, *, tz: ZoneInfo, agora: datetime
) -> set[int]:
    return _calcular(db, filtros, tz=tz, agora=agora)[1][ocorrencia]


def _calcular(
    db: Session, filtros: Filtros, *, tz: ZoneInfo, agora: datetime
) -> tuple[PainelControle, dict[Ocorrencia, set[int]]]:
    empresas = {e.id: EmpresaRef(e.id, e.codigo, e.nome) for e in db.scalars(select(Empresa))}
    id_empresa = next((i for i, e in empresas.items() if e.codigo == filtros.empresa), None)
    if filtros.empresa and id_empresa is None:
        id_empresa = -1
    prazos = prazos_por_rota(db)
    padrao = prazo_padrao_horas(db)

    def prazo(origem: int, destino: int | None) -> int:
        return prazos.get((origem, destino), padrao) if destino else padrao

    da_empresa = (
        or_(
            Transferencia.empresa_origem_id == id_empresa,
            Transferencia.empresa_destino_id == id_empresa,
        )
        if id_empresa is not None
        else None
    )

    condicoes = [condicao_entre_empresas()]
    if da_empresa is not None:
        condicoes.append(da_empresa)
    if filtros.data_inicial:
        condicoes.append(Transferencia.data_criacao >= _inicio_do_dia(filtros.data_inicial, tz))
    if filtros.data_final:
        condicoes.append(
            Transferencia.data_criacao < _inicio_do_dia(filtros.data_final + timedelta(days=1), tz)
        )

    cabecalhos = db.execute(
        select(
            Transferencia.id,
            Transferencia.numero_nota,
            Transferencia.empresa_origem_id,
            Transferencia.empresa_destino_id,
            Transferencia.empresa_entrada_id,
            Transferencia.status,
            Transferencia.data_criacao,
            Transferencia.data_processamento,
            Transferencia.valor_total,
            Transferencia.usuario_emissao,
            Transferencia.raw_data["itens_sem_saida"],
        ).where(*condicoes)
    ).all()

    refs: dict[int, TransferenciaRef] = {}
    fora_do_prazo: set[int] = set()
    rotas: dict[tuple[int, int], Rota] = {}
    emissores: dict[str, Emissor] = {}
    fiscal: list[ProblemaFiscal] = []
    sem_saida_por_transferencia: dict[int, list[dict[str, Any]]] = {}

    for (
        id_,
        numero,
        origem,
        destino,
        entrada,
        status,
        criada,
        processada,
        valor,
        usuario,
        sem_saida,
    ) in cabecalhos:
        ref = TransferenciaRef(
            id_,
            numero,
            empresas[origem],
            empresas.get(destino) if destino else None,
            status,
            criada,
            valor,
            usuario,
        )
        refs[id_] = ref
        horas_prazo = prazo(origem, destino)
        if status == STATUS_PROCESSADA and criada and processada:
            atrasou = _horas(criada, processada) > horas_prazo
        elif status == STATUS_PENDENTE and criada:
            atrasou = _horas(criada, agora) > horas_prazo
        else:
            atrasou = False
        if atrasou:
            fora_do_prazo.add(id_)
        if status == STATUS_PROCESSADA and sem_saida:
            sem_saida_por_transferencia[id_] = list(sem_saida)

        if destino and status != STATUS_CANCELADA:
            rota = rotas.get((origem, destino))
            if rota is None:
                rota = rotas[(origem, destino)] = Rota(
                    empresas[origem],
                    empresas[destino],
                    horas_prazo,
                    (origem, destino) not in prazos,
                )
            rota.enviadas += 1
            rota.valor_enviado += valor or 0
            if status == STATUS_PROCESSADA:
                rota.recebidas += 1
                if criada and processada:
                    rota._horas.append(_horas(criada, processada))
            elif status == STATUS_PENDENTE:
                rota.pendentes += 1
            if atrasou:
                rota.fora_do_prazo += 1

        if status == STATUS_CANCELADA:
            fiscal.append(ProblemaFiscal(ref, "CANCELADA", "Nota de saída cancelada."))
        elif entrada and destino and entrada != destino:
            fiscal.append(
                ProblemaFiscal(
                    ref,
                    "ENTRADA_OUTRA_EMPRESA",
                    f"Entrada registrada na empresa {empresas[entrada].codigo}, não no destino "
                    f"{empresas[destino].codigo}.",
                )
            )

    ids_periodo = list(refs)
    divergentes_itens: dict[int, list[ItemDivergente]] = defaultdict(list)
    if ids_periodo:
        preco = aliased(PrecoProdutoEmpresa)

        enviada_total = func.sum(TransferenciaItem.quantidade_solicitada)
        recebida_total = func.sum(func.coalesce(TransferenciaItem.quantidade_processada, 0))
        linhas = db.execute(
            select(
                TransferenciaItem.transferencia_id,
                TransferenciaItem.id_produto_erp,
                func.max(TransferenciaItem.descricao_produto),
                enviada_total,
                recebida_total,
                case(
                    (
                        func.count(TransferenciaItem.valor_total) == func.count(),
                        func.sum(TransferenciaItem.valor_total),
                    ),
                    else_=None,
                ),
                func.max(preco.custo_gerencial),
            )
            .join(Transferencia, Transferencia.id == TransferenciaItem.transferencia_id)
            .outerjoin(
                preco,
                and_(
                    preco.empresa_id == Transferencia.empresa_origem_id,
                    preco.id_produto == TransferenciaItem.id_produto_erp,
                    preco.id_subproduto == TransferenciaItem.codigo_produto,
                ),
            )
            .where(
                _algum_de(TransferenciaItem.transferencia_id, ids_periodo),
                Transferencia.status == STATUS_PROCESSADA,
                TransferenciaItem.quantidade_solicitada.is_not(None),
            )
            .group_by(TransferenciaItem.transferencia_id, TransferenciaItem.id_produto_erp)
            .having(enviada_total != recebida_total)
        ).all()
        for tid, produto, descricao, enviada, receb, valor_item, custo in linhas:
            assert enviada is not None
            diferenca = enviada - receb
            if valor_item is not None and enviada:
                unitario: Decimal | None = valor_item / enviada
            else:
                unitario = custo
            divergentes_itens[tid].append(
                ItemDivergente(
                    produto,
                    descricao,
                    enviada,
                    receb,
                    diferenca,
                    (diferenca * unitario).quantize(Decimal("0.01"))
                    if unitario is not None
                    else None,
                )
            )

        cfops = db.execute(
            select(
                TransferenciaItem.transferencia_id,
                TransferenciaItem.cfop_saida,
                TransferenciaItem.cfop_entrada,
            )
            .where(
                _algum_de(TransferenciaItem.transferencia_id, ids_periodo),
                or_(
                    and_(
                        TransferenciaItem.cfop_saida.is_not(None),
                        TransferenciaItem.cfop_saida.not_in(CFOPS_SAIDA),
                    ),
                    and_(
                        TransferenciaItem.cfop_entrada.is_not(None),
                        TransferenciaItem.cfop_entrada.not_in(CFOPS_ENTRADA),
                    ),
                ),
            )
            .distinct()
        ).all()
        por_transferencia: dict[int, tuple[set[str], set[str]]] = defaultdict(
            lambda: (set(), set())
        )
        for tid, cfop_saida, cfop_entrada in cfops:
            if cfop_saida and cfop_saida not in CFOPS_SAIDA:
                por_transferencia[tid][0].add(cfop_saida)
            if cfop_entrada and cfop_entrada not in CFOPS_ENTRADA:
                por_transferencia[tid][1].add(cfop_entrada)
        for tid, (saidas, entradas) in por_transferencia.items():
            if saidas:
                fiscal.append(
                    ProblemaFiscal(
                        refs[tid], "CFOP_SAIDA", f"CFOP de saída {', '.join(sorted(saidas))}."
                    )
                )
            if entradas:
                fiscal.append(
                    ProblemaFiscal(
                        refs[tid], "CFOP_ENTRADA", f"CFOP de entrada {', '.join(sorted(entradas))}."
                    )
                )

    if sem_saida_por_transferencia:
        produtos = {
            str(i.get("id_produto"))
            for itens in sem_saida_por_transferencia.values()
            for i in itens
        }
        custos = {
            (p.empresa_id, p.id_produto): p.custo_gerencial
            for p in db.scalars(
                select(PrecoProdutoEmpresa).where(PrecoProdutoEmpresa.id_produto.in_(produtos))
            )
        }
        nomes = {
            p.id_produto: p.descricao
            for p in db.scalars(select(Produto).where(Produto.id_produto.in_(produtos)))
        }
        for tid, itens in sem_saida_por_transferencia.items():
            destino_ref = refs[tid].destino
            for i in itens:
                produto = str(i.get("id_produto"))
                quantidade = _decimal(i.get("quantidade"))
                custo = custos.get((destino_ref.id, produto)) if destino_ref else None
                divergentes_itens[tid].append(
                    ItemDivergente(
                        produto,
                        i.get("descricao") or nomes.get(produto),
                        Decimal(0),
                        quantidade,
                        -quantidade,
                        (-quantidade * custo).quantize(Decimal("0.01"))
                        if custo is not None
                        else None,
                        sem_saida=True,
                    )
                )

    divergencias = [
        Divergencia(
            refs[tid], itens, sum((i.valor_diferenca or Decimal(0) for i in itens), Decimal(0))
        )
        for tid, itens in divergentes_itens.items()
    ]
    for d in divergencias:
        t = d.transferencia
        if t.destino and (rota := rotas.get((t.origem.id, t.destino.id))):
            rota.divergentes += 1

    ids_fiscal = {p.transferencia.id for p in fiscal}
    for id_, ref in refs.items():
        nome = ref.usuario_emissao or "Não informado"
        e = emissores.setdefault(nome, Emissor(nome))
        if ref.status != STATUS_CANCELADA:
            e.enviadas += 1
        e.fora_do_prazo += id_ in fora_do_prazo
        e.divergentes += id_ in divergentes_itens
        e.problemas_fiscais += id_ in ids_fiscal

    transito_cond = [condicao_entre_empresas(), Transferencia.status == STATUS_PENDENTE]
    if da_empresa is not None:
        transito_cond.append(da_empresa)
    transito = [
        TransitoDestino(
            empresas.get(destino) if destino else None, qtd, valor or Decimal(0), antiga
        )
        for destino, qtd, valor, antiga in db.execute(
            select(
                Transferencia.empresa_destino_id,
                func.count(),
                func.sum(Transferencia.valor_total),
                func.min(Transferencia.data_criacao),
            )
            .where(*transito_cond)
            .group_by(Transferencia.empresa_destino_id)
        )
    ]
    transito.sort(key=lambda t: t.valor, reverse=True)

    atencao = fora_do_prazo | set(divergentes_itens) | ids_fiscal
    tratativas = ultimas_tratativas(db, atencao)
    for tid, tratativa in tratativas.items():
        refs[tid].tratativa = tratativa
    sem_tratativa = {
        tid for tid in atencao if tid not in tratativas or tratativas[tid].situacao != "RESOLVIDA"
    }

    for rota in rotas.values():
        if rota._horas:
            rota.tempo_medio_horas = round(sum(rota._horas) / len(rota._horas), 1)

    divergencias.sort(key=lambda d: abs(d.valor_diferenca), reverse=True)
    fiscal.sort(key=lambda p: p.transferencia.data_criacao or agora, reverse=True)

    ocorrencias: dict[Ocorrencia, set[int]] = {
        "FORA_DO_PRAZO": fora_do_prazo,
        "DIVERGENTE": set(divergentes_itens),
        "FISCAL": ids_fiscal,
        "SEM_TRATATIVA": sem_tratativa,
    }
    painel = PainelControle(
        resumo=Resumo(
            em_transito_quantidade=sum(t.quantidade for t in transito),
            em_transito_valor=sum((t.valor for t in transito), Decimal(0)),
            fora_do_prazo=len(fora_do_prazo),
            divergentes=len(divergencias),
            valor_divergencia=sum((d.valor_diferenca for d in divergencias), Decimal(0)),
            problemas_fiscais=len(ids_fiscal),
            sem_tratativa=len(sem_tratativa),
        ),
        prazo_padrao_horas=padrao,
        em_transito=transito,
        rotas=sorted(rotas.values(), key=lambda r: (r.origem.codigo, r.destino.codigo)),
        divergencias=divergencias[:LIMITE_LISTAS],
        fiscal=fiscal[:LIMITE_LISTAS],
        emissores=sorted(
            emissores.values(),
            key=lambda e: (
                -(e.fora_do_prazo + e.divergentes + e.problemas_fiscais),
                -e.enviadas,
                e.usuario,
            ),
        ),
    )
    return painel, ocorrencias
