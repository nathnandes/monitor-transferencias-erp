from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.locais_perda import fora_da_perda
from app.database.models import Empresa, EstoqueEmpresaLocalLote, Produto
from app.services import excecoes_cobertura as excecoes
from app.services.estoque import (
    FALTA,
    EmpresaNaoEncontrada,
    JanelaVendas,
    StatusCobertura,
    _dias_vendas,
    _janela,
    _vendido,
    classificar_cobertura,
    descricao_item,
    fora_da_loja,
)

ALVO_PADRAO_DIAS = 30

EM_FALTA = FALTA
_CHAVES_POR_CONSULTA = 5000
_MILESIMO = Decimal("0.001")


@dataclass(frozen=True)
class ItemPedido:
    id_produto: str
    id_subproduto: str
    descricao: str | None
    marca: str | None
    status_cobertura: StatusCobertura
    saldo_loja: Decimal
    venda_media_diaria: Decimal
    cobertura_dias: Decimal | None
    necessidade: Decimal
    quantidade: Decimal
    disponivel_deposito: Decimal


@dataclass(frozen=True)
class PedidoDeposito:
    deposito: Empresa
    itens: list[ItemPedido]


@dataclass(frozen=True)
class PedidoAbastecimento:
    loja: Empresa
    janela: JanelaVendas
    alvo_dias: int

    tem_vendas: bool
    pedidos: list[PedidoDeposito]

    sem_estoque: list[ItemPedido]


def _empresa(db: Session, codigo: str) -> Empresa:
    empresa = db.scalar(select(Empresa).where(Empresa.codigo == codigo))
    if empresa is None:
        raise EmpresaNaoEncontrada(f"Empresa {codigo} não encontrada.")
    return empresa


def _disponivel_por_item(
    db: Session, empresa_id: int, chaves: Sequence[tuple[str, str]] | None = None
) -> dict[tuple[str, str], Decimal]:
    e = EstoqueEmpresaLocalLote
    consulta = (
        select(e.id_produto, e.id_subproduto, func.sum(e.saldo_disponivel))
        .where(e.empresa_id == empresa_id, e.ativo.is_(True), fora_da_perda(), fora_da_loja(e))
        .group_by(e.id_produto, e.id_subproduto)
    )
    if chaves is None:
        return {(p, s): d or Decimal(0) for p, s, d in db.execute(consulta)}
    saldos: dict[tuple[str, str], Decimal] = {}
    for inicio in range(0, len(chaves), _CHAVES_POR_CONSULTA):
        lote = chaves[inicio : inicio + _CHAVES_POR_CONSULTA]
        for p, s, d in db.execute(consulta.where(tuple_(e.id_produto, e.id_subproduto).in_(lote))):
            saldos[(p, s)] = d or Decimal(0)
    return saldos


def montar_pedido(
    db: Session,
    loja: str,
    janela: JanelaVendas | None = None,
    alvo_dias: int = ALVO_PADRAO_DIAS,
) -> PedidoAbastecimento:
    janela = _janela(janela)
    empresa = _empresa(db, loja)
    depositos = [
        d
        for codigo in get_settings().depositos_abastecimento
        if codigo != loja and (d := db.scalar(select(Empresa).where(Empresa.codigo == codigo)))
    ]
    dias = db.scalar(select(_dias_vendas(janela, empresa.id, "baixa").c.dias))
    if not dias:
        return PedidoAbastecimento(empresa, janela, alvo_dias, False, [], [])

    v = _vendido(janela, empresa.id, "baixa")
    medias = {
        (p, s): quantidade / Decimal(dias)
        for p, s, quantidade in db.execute(
            select(v.c.id_produto, v.c.id_subproduto, v.c.quantidade).where(v.c.quantidade > 0)
        )
    }
    saldo_loja = _disponivel_por_item(db, empresa.id)
    em_excecao = {(p, s) for e, p, s in excecoes.chaves(db) if e == empresa.id}

    faltas: dict[tuple[str, str], tuple[StatusCobertura, Decimal, Decimal | None, Decimal]] = {}
    alvo = Decimal(alvo_dias)
    for chave, media in medias.items():
        if chave in em_excecao:
            continue
        saldo = saldo_loja.get(chave, Decimal(0))
        cobertura, status = classificar_cobertura(saldo, media)
        if status not in EM_FALTA:
            continue
        necessidade = (media * alvo - max(saldo, Decimal(0))).to_integral_value(ROUND_CEILING)
        if necessidade > 0:
            faltas[chave] = (status, saldo, cobertura, necessidade)

    chaves = sorted(faltas)
    estoque_deposito = {d.id: _disponivel_por_item(db, d.id, chaves) for d in depositos}
    cadastro = {
        (p, s): (descricao, marca)
        for inicio in range(0, len(chaves), _CHAVES_POR_CONSULTA)
        for p, s, descricao, marca in db.execute(
            select(
                Produto.id_produto, Produto.id_subproduto, descricao_item(), Produto.marca
            ).where(
                tuple_(Produto.id_produto, Produto.id_subproduto).in_(
                    chaves[inicio : inicio + _CHAVES_POR_CONSULTA]
                )
            )
        )
    }

    por_deposito: dict[int, list[ItemPedido]] = defaultdict(list)
    sem_estoque: list[ItemPedido] = []
    for chave in chaves:
        status, saldo, cobertura, necessidade = faltas[chave]
        descricao, marca = cadastro.get(chave, (None, None))
        base = ItemPedido(
            chave[0],
            chave[1],
            descricao,
            marca,
            status,
            saldo,
            medias[chave].quantize(_MILESIMO),
            cobertura,
            necessidade.quantize(_MILESIMO),
            quantidade=Decimal(0).quantize(_MILESIMO),
            disponivel_deposito=Decimal(0),
        )

        com_saldo = sorted(
            (
                (estoque_deposito[d.id].get(chave, Decimal(0)), ordem, d)
                for ordem, d in enumerate(depositos)
            ),
            key=lambda x: (-x[0], x[1]),
        )
        falta = necessidade
        for disponivel, _, deposito in com_saldo:
            if falta <= 0 or disponivel <= 0:
                break
            quantidade = min(falta, disponivel)
            por_deposito[deposito.id].append(
                replace(
                    base, quantidade=quantidade.quantize(_MILESIMO), disponivel_deposito=disponivel
                )
            )
            falta -= quantidade
        if falta == necessidade:
            sem_estoque.append(base)

    def ordem(i: ItemPedido) -> tuple[bool, str, str, int, str]:

        return (
            i.marca is None,
            (i.marca or "").upper(),
            (i.descricao or "").upper(),
            len(i.id_subproduto),
            i.id_subproduto,
        )

    return PedidoAbastecimento(
        empresa,
        janela,
        alvo_dias,
        True,
        [PedidoDeposito(d, sorted(por_deposito[d.id], key=ordem)) for d in depositos],
        sorted(sem_estoque, key=ordem),
    )
