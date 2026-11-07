from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal, NamedTuple, cast

from sqlalchemy import (
    ColumnElement,
    Subquery,
    delete,
    false,
    func,
    or_,
    select,
    true,
    tuple_,
)
from sqlalchemy.orm import Session

from app.database.models import (
    Empresa,
    JustificativaAvulsa,
    MovimentoEstoque,
    NotaMovimento,
    ParametrosAvulsas,
    Produto,
    VinculoAvulsa,
)
from app.dominio.intervalo import Intervalo
from app.dominio.operacoes_estoque import CATALOGO
from app.services.estoque import descricao_item
from app.services.movimentos_estoque import (
    COI_BALANCO,
    COI_ENTRADA_AVULSA,
    COI_SAIDA_AVULSA,
    TIPOS,
)

TipoAvulsa = Literal["entrada_avulsa", "saida_avulsa"]
Situacao = Literal["pendente", "justificada", "todas"]

COIS_AVULSAS = (COI_ENTRADA_AVULSA, COI_SAIDA_AVULSA)
ENTRADA: tuple[TipoAvulsa, ...] = ("entrada_avulsa",)
SAIDA: tuple[TipoAvulsa, ...] = ("saida_avulsa",)
AMBAS: tuple[TipoAvulsa, ...] = ("entrada_avulsa", "saida_avulsa")


@dataclass(frozen=True)
class Motivo:
    codigo: str
    rotulo: str
    tipos: tuple[TipoAvulsa, ...]


MOTIVOS: tuple[Motivo, ...] = (
    Motivo("uso_consumo", "Uso e consumo", SAIDA),
    Motivo("avaria", "Avaria ou quebra", SAIDA),
    Motivo("vencimento", "Produto vencido", SAIDA),
    Motivo("perda_furto", "Perda ou furto", SAIDA),
    Motivo("brinde_doacao", "Brinde ou doação", SAIDA),
    Motivo("mercadoria_encontrada", "Mercadoria encontrada", ENTRADA),
    Motivo("devolucao_sem_nota", "Devolução sem nota", ENTRADA),
    Motivo("correcao_lancamento", "Correção de lançamento", AMBAS),
    Motivo("ajuste_inventario", "Ajuste de inventário", AMBAS),
    Motivo("outro", "Outro (descreva)", AMBAS),
)
POR_CODIGO = {m.codigo: m for m in MOTIVOS}

MOTIVOS_COM_OBSERVACAO = frozenset({"outro"})


JANELA_CANDIDATOS_DIAS = 30
LIMITE_CANDIDATOS = 20
MOTIVO_DO_VINCULO = "correcao_lancamento"


COIS_USO_CONSUMO = tuple(
    sorted(o.coi for o in CATALOGO.values() if o.saida and o.categoria == "uso_consumo")
)


@dataclass(frozen=True)
class Regra:
    codigo: str
    rotulo: str
    cois: tuple[int, ...]
    janela_dias: int | None = None


REGRAS: tuple[Regra, ...] = (
    Regra("balanco", "O último balanço tirou o produto", (COI_BALANCO,)),
    Regra("uso_consumo", "Saiu para uso e consumo e voltou", COIS_USO_CONSUMO, 90),
)
REGRAS_POR_CODIGO = {r.codigo: r for r in REGRAS}


LIMITE_LOTE = 200


CHAVES_POR_CONSULTA = 500


def _em_lotes[T](chaves: Iterable[T], tamanho: int = CHAVES_POR_CONSULTA) -> Iterator[list[T]]:
    lista = list(chaves)
    for inicio in range(0, len(lista), tamanho):
        yield lista[inicio : inicio + tamanho]


class JustificativaInvalida(ValueError):
    pass


class DocumentoNaoAvulso(LookupError):
    pass


class VinculoInvalido(ValueError):
    pass


class JaRelacionado(VinculoInvalido):
    pass


@dataclass(frozen=True)
class Vinculo:
    id_planilha: str
    dia: date | None
    tipo: TipoAvulsa
    usuario_nome: str
    criado_em: datetime


@dataclass(frozen=True)
class Alerta:
    regra: str
    id_produto: str
    id_subproduto: str
    descricao: str | None
    dia: date
    id_planilha: str
    numero: str | None
    operacao: str | None
    quantidade: Decimal
    valor: Decimal


@dataclass(frozen=True)
class Candidato:
    id_planilha: str
    dia: date
    tipo: TipoAvulsa
    itens: int
    quantidade: Decimal
    valor: Decimal
    em_comum: int
    exato: bool
    id_produto: str
    id_subproduto: str
    descricao: str | None
    justificativa: JustificativaAvulsa | None


@dataclass(frozen=True)
class DocumentoAvulso:
    empresa: Empresa
    id_planilha: str
    dia: date
    tipo: TipoAvulsa
    itens: int
    quantidade: Decimal
    valor: Decimal

    id_produto: str
    id_subproduto: str
    descricao: str | None
    exige: bool
    justificativa: JustificativaAvulsa | None
    vinculo: Vinculo | None = None
    alertas: Sequence[Alerta] = ()


@dataclass(frozen=True)
class Pendencias:
    documentos: int
    valor: Decimal


@dataclass(frozen=True)
class PaginaDocumentos:
    total: int
    documentos: Sequence[DocumentoAvulso]
    pendentes: Pendencias
    pendentes_desde_o_corte: Pendencias
    justificadas: int


def _documentos(
    *,
    periodo: Intervalo | None = None,
    a_partir: date | None = None,
    empresa: Empresa | None,
    tipo: TipoAvulsa | None,
) -> Subquery:
    m = MovimentoEstoque
    condicoes: list[ColumnElement[bool]] = [m.coi.in_(COIS_AVULSAS)]
    if periodo is not None:
        condicoes.append(m.dia.between(periodo.inicio, periodo.fim))
    if a_partir is not None:
        condicoes.append(m.dia >= a_partir)
    if empresa is not None:
        condicoes.append(m.empresa_id == empresa.id)
    if tipo is not None:
        condicoes.append(m.tipo == tipo)
    return (
        select(
            m.empresa_id.label("empresa_id"),
            m.id_planilha.label("id_planilha"),
            func.max(m.dia).label("dia"),
            func.min(m.coi).label("coi"),
            func.count().label("itens"),
            func.sum(m.quantidade).label("quantidade"),
            func.sum(m.valor).label("valor"),
            func.min(
                func.lpad(func.coalesce(m.sequencia, ""), 10, "0")
                + "|"
                + m.id_produto
                + "|"
                + m.id_subproduto
            ).label("primeiro"),
        )
        .where(*condicoes)
        .group_by(m.empresa_id, m.id_planilha)
        .subquery("documentos")
    )


def listar_documentos(
    db: Session,
    *,
    periodo: Intervalo,
    desde: date | None,
    empresa: Empresa | None = None,
    tipo: TipoAvulsa | None = None,
    situacao: Situacao = "pendente",
    alerta: str | None = None,
    pagina: int = 1,
    tamanho_pagina: int = 50,
) -> PaginaDocumentos:
    j = JustificativaAvulsa
    docs = _documentos(periodo=periodo, empresa=empresa, tipo=tipo)
    d = docs.c
    juntar = (j.empresa_id == d.empresa_id) & (j.id_planilha == d.id_planilha)
    pendente = j.id_planilha.is_(None) & (d.dia >= desde if desde is not None else true())

    total_todas, n_pend, valor_pend, n_just = db.execute(
        select(
            func.count(),
            func.count().filter(pendente),
            func.sum(func.abs(d.valor)).filter(pendente),
            func.count(j.id_planilha),
        )
        .select_from(docs)
        .outerjoin(j, juntar)
    ).one()
    total = {"pendente": n_pend, "justificada": n_just, "todas": total_todas}[situacao]

    filtro: list[ColumnElement[bool]] = []
    if situacao == "pendente":
        filtro.append(pendente)
    elif situacao == "justificada":
        filtro.append(j.id_planilha.is_not(None))
    if alerta is not None:
        entradas = (
            select(d.empresa_id, d.id_planilha, d.dia)
            .select_from(docs)
            .outerjoin(j, juntar)
            .where(*filtro, d.coi == COI_ENTRADA_AVULSA)
            .subquery("entradas")
        )
        com_alerta = _com_aviso(db, entradas, REGRAS_POR_CODIGO[alerta])

        com_alerta.sort(key=lambda x: x.id_planilha, reverse=True)
        com_alerta.sort(key=lambda x: (-x.dia.toordinal(), x.empresa_id, -len(x.id_planilha)))
        da_pagina = {
            (x.empresa_id, x.id_planilha)
            for x in com_alerta[(pagina - 1) * tamanho_pagina : pagina * tamanho_pagina]
        }
        filtro.append(tuple_(d.empresa_id, d.id_planilha).in_(da_pagina) if da_pagina else false())
        total = len(com_alerta)
    linhas = db.execute(
        select(
            d.empresa_id, d.id_planilha, d.dia, d.coi, d.itens, d.quantidade, d.valor, d.primeiro, j
        )
        .select_from(docs)
        .outerjoin(j, juntar)
        .where(*filtro)
        .order_by(
            d.dia.desc(),
            d.empresa_id,
            func.length(d.id_planilha).desc(),
            d.id_planilha.desc(),
        )
        .offset((pagina - 1) * tamanho_pagina if alerta is None else 0)
        .limit(tamanho_pagina)
    ).all()

    chaves = {(x.empresa_id, x.id_planilha) for x in linhas}
    itens = _itens(db, chaves)
    descricoes = {
        (eid, planilha, i.id_produto, i.id_subproduto): i.descricao
        for (eid, planilha), lista in itens.items()
        for i in lista
    }
    vinculos = _vinculos(db, chaves)
    alertas = _alertas(
        db,
        [
            (x.empresa_id, x.id_planilha, x.dia, itens.get((x.empresa_id, x.id_planilha), []))
            for x in linhas
            if x.coi == COI_ENTRADA_AVULSA
        ],
    )
    empresas = {
        e.id: e
        for e in db.scalars(select(Empresa).where(Empresa.id.in_({x.empresa_id for x in linhas})))
    }
    documentos = []
    for x in linhas:
        _, prod, sub = x.primeiro.split("|")
        documentos.append(
            DocumentoAvulso(
                empresa=empresas[x.empresa_id],
                id_planilha=x.id_planilha,
                dia=x.dia,
                tipo=cast(TipoAvulsa, TIPOS[x.coi]),
                itens=x.itens,
                quantidade=x.quantidade or Decimal(0),
                valor=x.valor or Decimal(0),
                id_produto=prod,
                id_subproduto=sub,
                descricao=descricoes.get((x.empresa_id, x.id_planilha, prod, sub)),
                exige=desde is None or x.dia >= desde,
                justificativa=x.JustificativaAvulsa,
                vinculo=vinculos.get((x.empresa_id, x.id_planilha)),
                alertas=alertas.get((x.empresa_id, x.id_planilha), ()),
            )
        )
    return PaginaDocumentos(
        total=total,
        documentos=documentos,
        pendentes=Pendencias(n_pend, valor_pend or Decimal(0)),
        pendentes_desde_o_corte=pendencias_desde(db, desde=desde, empresa=empresa, tipo=tipo),
        justificadas=n_just,
    )


@dataclass(frozen=True)
class _Item:
    id_produto: str
    id_subproduto: str
    quantidade: Decimal
    valor: Decimal
    descricao: str | None


def _itens(db: Session, documentos: set[tuple[int, str]]) -> dict[tuple[int, str], list[_Item]]:
    if not documentos:
        return {}
    m = MovimentoEstoque
    resultado: dict[tuple[int, str], list[_Item]] = defaultdict(list)
    for lote in _em_lotes(documentos):
        for eid, planilha, prod, sub, qtd, valor, desc in db.execute(
            select(
                m.empresa_id,
                m.id_planilha,
                m.id_produto,
                m.id_subproduto,
                func.sum(m.quantidade),
                func.sum(m.valor),
                func.max(func.coalesce(m.descricao_produto, descricao_item())),
            )
            .outerjoin(
                Produto,
                (Produto.id_produto == m.id_produto) & (Produto.id_subproduto == m.id_subproduto),
            )
            .where(
                m.coi.in_(COIS_AVULSAS),
                tuple_(m.empresa_id, m.id_planilha).in_(lote),
            )
            .group_by(m.empresa_id, m.id_planilha, m.id_produto, m.id_subproduto)
        ):
            resultado[(eid, planilha)].append(
                _Item(prod, sub, qtd or Decimal(0), valor or Decimal(0), desc)
            )
    return resultado


def _vinculos(db: Session, documentos: set[tuple[int, str]]) -> dict[tuple[int, str], Vinculo]:
    if not documentos:
        return {}
    v = VinculoAvulsa
    empresas = {eid for eid, _ in documentos}
    planilhas = {planilha for _, planilha in documentos}
    pares = list(
        db.scalars(
            select(v).where(
                v.empresa_id.in_(empresas),
                or_(v.entrada_id_planilha.in_(planilhas), v.saida_id_planilha.in_(planilhas)),
            )
        )
    )
    dias = _dias(
        db,
        {(x.empresa_id, x.entrada_id_planilha) for x in pares}
        | {(x.empresa_id, x.saida_id_planilha) for x in pares},
    )
    resultado: dict[tuple[int, str], Vinculo] = {}
    for x in pares:
        e, s = (x.empresa_id, x.entrada_id_planilha), (x.empresa_id, x.saida_id_planilha)
        resultado[e] = Vinculo(s[1], dias.get(s), "saida_avulsa", x.usuario_nome, x.created_at)
        resultado[s] = Vinculo(e[1], dias.get(e), "entrada_avulsa", x.usuario_nome, x.created_at)
    return {k: val for k, val in resultado.items() if k in documentos}


def _dias(db: Session, documentos: set[tuple[int, str]]) -> dict[tuple[int, str], date]:
    if not documentos:
        return {}
    m = MovimentoEstoque
    return {
        (eid, planilha): dia
        for eid, planilha, dia in db.execute(
            select(m.empresa_id, m.id_planilha, func.max(m.dia))
            .where(m.coi.in_(COIS_AVULSAS), tuple_(m.empresa_id, m.id_planilha).in_(documentos))
            .group_by(m.empresa_id, m.id_planilha)
        )
    }


def _alertas(
    db: Session,
    entradas: Sequence[tuple[int, str, date, Sequence[_Item]]],
    *,
    regras: Sequence[Regra] = REGRAS,
) -> dict[tuple[int, str], list[Alerta]]:
    produtos = {
        (eid, i.id_produto, i.id_subproduto) for eid, _, _, itens in entradas for i in itens
    }
    if not produtos:
        return {}
    m = MovimentoEstoque
    ate = max(dia for _, _, dia, _ in entradas)
    resultado: dict[tuple[int, str], list[Alerta]] = defaultdict(list)
    for regra in regras:
        janela = timedelta(days=regra.janela_dias) if regra.janela_dias is not None else None
        condicoes = [
            m.coi.in_(regra.cois),
            m.dia <= ate,
            m.quantidade != 0,
        ]
        if janela is not None:
            condicoes.append(m.dia >= min(dia for _, _, dia, _ in entradas) - janela)
        movimentos: dict[
            tuple[int, str, str], list[tuple[date, str, str | None, Decimal, Decimal]]
        ] = defaultdict(list)
        for lote in _em_lotes(produtos):
            for eid, prod, sub, dia, planilha, operacao, qtd, valor in db.execute(
                select(
                    m.empresa_id,
                    m.id_produto,
                    m.id_subproduto,
                    m.dia,
                    m.id_planilha,
                    func.max(m.operacao),
                    func.sum(m.quantidade),
                    func.sum(func.coalesce(m.valor, 0)),
                )
                .where(*condicoes, tuple_(m.empresa_id, m.id_produto, m.id_subproduto).in_(lote))
                .group_by(m.empresa_id, m.id_produto, m.id_subproduto, m.dia, m.id_planilha)
            ):
                movimentos[(eid, prod, sub)].append(
                    (dia, planilha, operacao, qtd or Decimal(0), valor or Decimal(0))
                )
        for eid, planilha, dia, itens in entradas:
            for i in itens:
                anteriores = [
                    x
                    for x in movimentos.get((eid, i.id_produto, i.id_subproduto), [])
                    if x[0] <= dia and (janela is None or x[0] >= dia - janela)
                ]
                if not anteriores:
                    continue

                x_dia, x_planilha, operacao, qtd, valor = max(
                    anteriores, key=lambda x: (x[0], len(x[1]), x[1])
                )
                if qtd < 0:
                    resultado[(eid, planilha)].append(
                        Alerta(
                            regra=regra.codigo,
                            id_produto=i.id_produto,
                            id_subproduto=i.id_subproduto,
                            descricao=i.descricao,
                            dia=x_dia,
                            id_planilha=x_planilha,
                            numero=None,
                            operacao=operacao,
                            quantidade=qtd,
                            valor=valor,
                        )
                    )

    notas = {(eid, a.id_planilha) for (eid, _), lista in resultado.items() for a in lista}
    n = NotaMovimento
    numeros = {
        (eid, planilha): numero
        for lote in _em_lotes(notas)
        for eid, planilha, numero in db.execute(
            select(n.empresa_id, n.id_planilha, n.numero).where(
                tuple_(n.empresa_id, n.id_planilha).in_(lote), n.numero.is_not(None)
            )
        )
    }
    return {
        chave: [replace(a, numero=numeros.get((chave[0], a.id_planilha))) for a in lista]
        for chave, lista in resultado.items()
    }


class _Entrada(NamedTuple):
    empresa_id: int
    id_planilha: str
    dia: date


def _com_aviso(db: Session, entradas: Subquery, regra: Regra) -> list[_Entrada]:
    m = MovimentoEstoque
    e = entradas.c
    produtos = (
        select(e.empresa_id, e.id_planilha, e.dia, m.id_produto, m.id_subproduto)
        .join(m, (m.empresa_id == e.empresa_id) & (m.id_planilha == e.id_planilha))
        .where(m.coi == COI_ENTRADA_AVULSA)
        .distinct()
    )
    por_produto: dict[tuple[int, str, str], list[tuple[str, date]]] = defaultdict(list)
    for eid, planilha, dia, prod, sub in db.execute(produtos):
        por_produto[(eid, prod, sub)].append((planilha, dia))
    if not por_produto:
        return []
    dias = [dia for lista in por_produto.values() for _, dia in lista]
    janela = timedelta(days=regra.janela_dias) if regra.janela_dias is not None else None
    sub_produtos = produtos.subquery("produtos")
    condicoes = [
        m.coi.in_(regra.cois),
        m.dia <= max(dias),
        m.quantidade != 0,
        tuple_(m.empresa_id, m.id_produto, m.id_subproduto).in_(
            select(
                sub_produtos.c.empresa_id, sub_produtos.c.id_produto, sub_produtos.c.id_subproduto
            )
        ),
    ]
    if janela is not None:
        condicoes.append(m.dia >= min(dias) - janela)
    movimentos: dict[tuple[int, str, str], list[tuple[date, str, Decimal]]] = defaultdict(list)
    for eid, prod, sub, dia, planilha, qtd in db.execute(
        select(
            m.empresa_id,
            m.id_produto,
            m.id_subproduto,
            m.dia,
            m.id_planilha,
            func.sum(m.quantidade),
        )
        .where(*condicoes)
        .group_by(m.empresa_id, m.id_produto, m.id_subproduto, m.dia, m.id_planilha)
    ):
        movimentos[(eid, prod, sub)].append((dia, planilha, qtd or Decimal(0)))
    com: dict[tuple[int, str], date] = {}
    for (eid, prod, sub), lista in movimentos.items():
        for planilha, dia in por_produto[(eid, prod, sub)]:
            anteriores = [
                x for x in lista if x[0] <= dia and (janela is None or x[0] >= dia - janela)
            ]

            if anteriores and max(anteriores, key=lambda x: (x[0], len(x[1]), x[1]))[2] < 0:
                com[(eid, planilha)] = dia
    return [_Entrada(eid, planilha, dia) for (eid, planilha), dia in com.items()]


def pendencias_desde(
    db: Session,
    *,
    desde: date | None,
    empresa: Empresa | None = None,
    tipo: TipoAvulsa | None = None,
) -> Pendencias:
    j = JustificativaAvulsa
    docs = _documentos(a_partir=desde, empresa=empresa, tipo=tipo)
    d = docs.c
    n, valor = db.execute(
        select(func.count(), func.sum(func.abs(d.valor)))
        .select_from(docs)
        .outerjoin(j, (j.empresa_id == d.empresa_id) & (j.id_planilha == d.id_planilha))
        .where(j.id_planilha.is_(None))
    ).one()
    return Pendencias(n, valor or Decimal(0))


@dataclass(frozen=True)
class Corte:
    dia: date | None
    usuario_nome: str | None
    atualizado_em: datetime | None


def corte(db: Session, padrao: date | None) -> Corte:
    p = db.get(ParametrosAvulsas, 1)
    if p is None:
        return Corte(padrao, None, None)
    return Corte(p.justificar_desde, p.usuario_nome, p.updated_at)


def definir_corte(
    db: Session, dia: date | None, *, usuario_id: int, usuario_nome: str, agora: datetime
) -> Corte:
    p = db.get(ParametrosAvulsas, 1)
    if p is None:
        p = ParametrosAvulsas(id=1)
        db.add(p)
    p.justificar_desde = dia
    p.usuario_id = usuario_id
    p.usuario_nome = usuario_nome
    p.updated_at = agora
    db.flush()
    return Corte(dia, usuario_nome, agora)


def tipo_do_documento(db: Session, empresa: Empresa, id_planilha: str) -> TipoAvulsa | None:
    m = MovimentoEstoque
    coi = db.scalar(
        select(m.coi)
        .where(m.empresa_id == empresa.id, m.id_planilha == id_planilha, m.coi.in_(COIS_AVULSAS))
        .limit(1)
    )
    return cast(TipoAvulsa, TIPOS[coi]) if coi is not None else None


def justificar(
    db: Session,
    empresa: Empresa,
    id_planilha: str,
    *,
    motivo: str,
    observacao: str | None,
    usuario_id: int,
    usuario_nome: str,
    agora: datetime,
) -> JustificativaAvulsa | None:
    tipo = tipo_do_documento(db, empresa, id_planilha)
    if tipo is None:
        return None
    texto = _validar(tipo, motivo, observacao)
    return _gravar(db, empresa, id_planilha, motivo, texto, usuario_id, usuario_nome, agora)


def _validar(tipo: TipoAvulsa, motivo: str, observacao: str | None) -> str | None:
    item = POR_CODIGO.get(motivo)
    if item is None or tipo not in item.tipos:
        rotulo = "entrada" if tipo == "entrada_avulsa" else "saída"
        raise JustificativaInvalida(f"Motivo {motivo!r} não vale para {rotulo} avulsa.")
    texto = (observacao or "").strip() or None
    if motivo in MOTIVOS_COM_OBSERVACAO and texto is None:
        raise JustificativaInvalida(f"Descreva o motivo na observação ({item.rotulo}).")
    return texto


def _gravar(
    db: Session,
    empresa: Empresa,
    id_planilha: str,
    motivo: str,
    texto: str | None,
    usuario_id: int,
    usuario_nome: str,
    agora: datetime,
) -> JustificativaAvulsa:
    registro = db.get(JustificativaAvulsa, (empresa.id, id_planilha))
    if registro is None:
        registro = JustificativaAvulsa(empresa_id=empresa.id, id_planilha=id_planilha)
        db.add(registro)
    registro.motivo = motivo
    registro.observacao = texto
    registro.pelo_vinculo = False
    registro.usuario_id = usuario_id
    registro.usuario_nome = usuario_nome
    registro.updated_at = agora
    db.flush()
    db.refresh(registro)
    return registro


def justificar_varios(
    db: Session,
    documentos: Sequence[tuple[Empresa, str]],
    *,
    motivo: str,
    observacao: str | None,
    usuario_id: int,
    usuario_nome: str,
    agora: datetime,
) -> list[JustificativaAvulsa]:
    unicos = list(dict.fromkeys((e.id, p) for e, p in documentos))
    empresas = {e.id: e for e, _ in documentos}
    texto: str | None = None
    for eid, id_planilha in unicos:
        tipo = tipo_do_documento(db, empresas[eid], id_planilha)
        if tipo is None:
            raise DocumentoNaoAvulso(
                f"Documento {id_planilha} não é uma entrada ou saída avulsa da empresa "
                f"{empresas[eid].codigo}."
            )
        try:
            texto = _validar(tipo, motivo, observacao)
        except JustificativaInvalida as exc:
            raise JustificativaInvalida(f"Documento {id_planilha}: {exc}") from exc
    return [
        _gravar(db, empresas[eid], p, motivo, texto, usuario_id, usuario_nome, agora)
        for eid, p in unicos
    ]


def vinculo_do_documento(db: Session, empresa: Empresa, id_planilha: str) -> VinculoAvulsa | None:
    v = VinculoAvulsa
    return db.scalar(
        select(v).where(
            v.empresa_id == empresa.id,
            or_(v.entrada_id_planilha == id_planilha, v.saida_id_planilha == id_planilha),
        )
    )


def par_do_documento(db: Session, empresa: Empresa, id_planilha: str) -> Vinculo | None:
    return _vinculos(db, {(empresa.id, id_planilha)}).get((empresa.id, id_planilha))


def candidatos(
    db: Session, empresa: Empresa, id_planilha: str, *, limite: int = LIMITE_CANDIDATOS
) -> list[Candidato] | None:
    tipo = tipo_do_documento(db, empresa, id_planilha)
    if tipo is None:
        return None
    meus = _itens(db, {(empresa.id, id_planilha)}).get((empresa.id, id_planilha), [])
    dia = _dias(db, {(empresa.id, id_planilha)})[(empresa.id, id_planilha)]
    if not meus:
        return []
    outro_coi = COI_SAIDA_AVULSA if tipo == "entrada_avulsa" else COI_ENTRADA_AVULSA
    m = MovimentoEstoque
    janela = timedelta(days=JANELA_CANDIDATOS_DIAS)
    planilhas = set(
        db.scalars(
            select(m.id_planilha)
            .where(
                m.empresa_id == empresa.id,
                m.coi == outro_coi,
                m.dia.between(dia - janela, dia + janela),
                tuple_(m.id_produto, m.id_subproduto).in_(
                    {(i.id_produto, i.id_subproduto) for i in meus}
                ),
            )
            .distinct()
        )
    )
    ja = _vinculos(db, {(empresa.id, p) for p in planilhas})
    planilhas = {p for p in planilhas if (empresa.id, p) not in ja}
    if not planilhas:
        return []
    chaves = {(empresa.id, p) for p in planilhas}
    itens = _itens(db, chaves)
    dias = _dias(db, chaves)
    justificativas = {
        j.id_planilha: j
        for j in db.scalars(
            select(JustificativaAvulsa).where(
                JustificativaAvulsa.empresa_id == empresa.id,
                JustificativaAvulsa.id_planilha.in_(planilhas),
            )
        )
    }
    meu_mapa = {(i.id_produto, i.id_subproduto): abs(i.quantidade) for i in meus}
    resultado = []
    for p in planilhas:
        dele = itens.get((empresa.id, p), [])
        mapa = {(i.id_produto, i.id_subproduto): abs(i.quantidade) for i in dele}
        comuns = [i for i in dele if (i.id_produto, i.id_subproduto) in meu_mapa]
        primeiro = comuns[0] if comuns else dele[0]
        resultado.append(
            Candidato(
                id_planilha=p,
                dia=dias[(empresa.id, p)],
                tipo=cast(TipoAvulsa, TIPOS[outro_coi]),
                itens=len(dele),
                quantidade=sum((i.quantidade for i in dele), Decimal(0)),
                valor=sum((i.valor for i in dele), Decimal(0)),
                em_comum=len(comuns),
                exato=mapa == meu_mapa,
                id_produto=primeiro.id_produto,
                id_subproduto=primeiro.id_subproduto,
                descricao=primeiro.descricao,
                justificativa=justificativas.get(p),
            )
        )
    resultado.sort(key=lambda c: (not c.exato, -c.em_comum, abs((c.dia - dia).days), c.id_planilha))
    return resultado[:limite]


def relacionar(
    db: Session,
    empresa: Empresa,
    id_planilha: str,
    outro_id_planilha: str,
    *,
    usuario_id: int,
    usuario_nome: str,
    agora: datetime,
) -> VinculoAvulsa | None:
    tipos = {p: tipo_do_documento(db, empresa, p) for p in (id_planilha, outro_id_planilha)}
    if None in tipos.values():
        return None
    if tipos[id_planilha] == tipos[outro_id_planilha]:
        raise VinculoInvalido("Relacione uma entrada avulsa com uma saída avulsa.")
    entrada, saida = (
        (id_planilha, outro_id_planilha)
        if tipos[id_planilha] == "entrada_avulsa"
        else (outro_id_planilha, id_planilha)
    )
    for p in (entrada, saida):
        existente = vinculo_do_documento(db, empresa, p)
        if existente is not None:
            par = (
                existente.saida_id_planilha
                if existente.entrada_id_planilha == p
                else existente.entrada_id_planilha
            )
            raise JaRelacionado(f"O documento {p} já está relacionado com o {par}.")
    vinculo = VinculoAvulsa(
        empresa_id=empresa.id,
        entrada_id_planilha=entrada,
        saida_id_planilha=saida,
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
    )
    db.add(vinculo)
    dias = _dias(db, {(empresa.id, entrada), (empresa.id, saida)})
    for p, outro, rotulo in (
        (entrada, saida, "saída"),
        (saida, entrada, "entrada"),
    ):
        if db.get(JustificativaAvulsa, (empresa.id, p)) is not None:
            continue
        dia_outro = dias.get((empresa.id, outro))
        quando = f" de {dia_outro.strftime('%d/%m/%Y')}" if dia_outro else ""
        db.add(
            JustificativaAvulsa(
                empresa_id=empresa.id,
                id_planilha=p,
                motivo=MOTIVO_DO_VINCULO,
                observacao=f"Relacionada com a {rotulo} avulsa {outro}{quando}.",
                pelo_vinculo=True,
                usuario_id=usuario_id,
                usuario_nome=usuario_nome,
                updated_at=agora,
            )
        )
    db.flush()
    db.refresh(vinculo)
    return vinculo


def desfazer_vinculo(db: Session, empresa: Empresa, id_planilha: str) -> bool:
    vinculo = vinculo_do_documento(db, empresa, id_planilha)
    if vinculo is None:
        return False
    j = JustificativaAvulsa
    db.execute(
        delete(j).where(
            j.empresa_id == empresa.id,
            j.id_planilha.in_((vinculo.entrada_id_planilha, vinculo.saida_id_planilha)),
            j.pelo_vinculo.is_(True),
        )
    )
    db.delete(vinculo)
    db.flush()
    return True
