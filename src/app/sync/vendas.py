from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial

from sqlalchemy import and_, delete, exists, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import (
    Devolucao,
    Venda,
    VendaDia,
    VendaItem,
    VendaTitulo,
    Vendedor,
)
from app.dominio.canais_venda import CANAIS, COIS_DEVOLUCAO, COIS_VENDA, SERIE_RECEBIMENTO_VENDA
from app.erp.errors import ErpApiError
from app.erp.servicos import (
    ROTA_ITENS_ENTRADA,
    ROTA_ITENS_SAIDA,
    ROTA_NOTAS_ENTRADA,
    ROTA_NOTAS_SAIDA,
    ROTA_RECEBIMENTOS_SAIDA,
    ItemNota,
    Nota,
    Recebimento,
    RegistroInvalidoError,
    ServicosErp,
    mapear_nota,
    mapear_recebimento,
    nome_da_pessoa,
)
from app.sync import por_dia
from app.sync.comum import (
    FabricaSessao,
    PoliticaRetry,
    RegistroErros,
    agora_utc,
    com_retry,
    finalizar_execucao_isolada,
    iniciar_execucao,
    resumir,
)
from app.sync.empresas import ResultadoSincronizacao
from app.sync.transferencias import (
    Resultado,
    _Empresas,
    _falhou,
    _fechar,
    _Leitor,
)

logger = get_logger(__name__)

TIPO = "vendas"


VERSAO_DIA = 3


VENDEDOR_SEM_NOME_REPETIR = timedelta(days=7)
VENDEDOR_NOME_REPETIR = timedelta(days=30)

VENDEDORES_POR_CICLO = 200

Relogio = Callable[[], datetime]


Titulos = dict[tuple[str, str, str], Recebimento]


TITULOS_POR_INSERT = 1000


@dataclass
class LeituraDia:
    notas: list[tuple[Nota, list[ItemNota]]] = field(default_factory=list)

    titulos: Titulos = field(default_factory=dict)
    titulos_pagos: Titulos = field(default_factory=dict)
    devolucoes: list[tuple[Nota, list[ItemNota]]] = field(default_factory=list)

    completo: bool = True


def dias_a_ler(
    db: Session,
    empresa_id: int,
    *,
    hoje: date,
    janela_dias: int,
    historico_dias: int,
    dias_por_ciclo: int,
) -> list[date]:
    return por_dia.dias_a_ler(
        db,
        VendaDia,
        empresa_id,
        versao=VERSAO_DIA,
        hoje=hoje,
        janela_dias=janela_dias,
        historico_dias=historico_dias,
        dias_por_ciclo=dias_por_ciclo,
    )


def sincronizar_vendas(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    ambiente: str,
    empresas: tuple[str, ...],
    politica: PoliticaRetry,
    janela_dias: int,
    historico_dias: int,
    dias_por_ciclo: int,
    agora: Relogio = agora_utc,
) -> ResultadoSincronizacao:
    return por_dia.sincronizar_por_dia(
        fabrica,
        servicos,
        tipo=TIPO,
        modelo_dia=VendaDia,
        versao=VERSAO_DIA,
        sincronizar_empresa=sincronizar_vendas_empresa,
        ambiente=ambiente,
        empresas=empresas,
        politica=politica,
        janela_dias=janela_dias,
        historico_dias=historico_dias,
        dias_por_ciclo=dias_por_ciclo,
        agora=agora,
        depois_das_empresas=lambda erros: atualizar_vendedores(
            fabrica, servicos, politica=politica, erros=erros, agora=agora
        ),
    )


def vendedores_a_consultar(db: Session, agora: datetime, limite: int) -> list[str]:
    vencido = or_(
        Vendedor.id_erp.is_(None),
        and_(Vendedor.nome.is_(None), Vendedor.consultado_em < agora - VENDEDOR_SEM_NOME_REPETIR),
        Vendedor.consultado_em < agora - VENDEDOR_NOME_REPETIR,
    )
    return list(
        db.scalars(
            select(Venda.id_vendedor)
            .distinct()
            .outerjoin(Vendedor, Vendedor.id_erp == Venda.id_vendedor)
            .where(Venda.id_vendedor.is_not(None), vencido)
            .order_by(Venda.id_vendedor)
            .limit(limite)
        )
    )


def atualizar_vendedores(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    politica: PoliticaRetry,
    erros: RegistroErros,
    agora: Relogio = agora_utc,
    limite: int = VENDEDORES_POR_CICLO,
) -> int:
    with fabrica() as db:
        pendentes = vendedores_a_consultar(db, agora(), limite)
    achados = 0
    for id_vendedor in pendentes:
        nome: str | None = None
        try:
            for saida in (True, False):
                pagina = com_retry(
                    partial(servicos.pagina_notas_da_pessoa, saida, id_vendedor, 1),
                    politica,
                    lambda exc, t: erros.erpapi(exc, tentativa=t),
                )
                if nome := nome_da_pessoa(pagina.registros):
                    break
        except ErpApiError:
            break
        valores = {"nome": nome, "consultado_em": agora()}
        with fabrica() as db, db.begin():
            db.execute(
                insert(Vendedor)
                .values(id_erp=id_vendedor, **valores)
                .on_conflict_do_update(index_elements=["id_erp"], set_=valores)
            )
        achados += nome is not None
    if pendentes:
        logger.info("sync.vendas.vendedores consultados=%s com_nome=%s", len(pendentes), achados)
    return achados


def sincronizar_vendas_empresa(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    cadastro: _Empresas,
    *,
    id_erp: str,
    dias: list[date],
    pai_id: int | None,
    politica: PoliticaRetry,
    agora: Relogio = agora_utc,
) -> Resultado:
    empresa_id = cadastro.por_id_erp[id_erp]
    execucao_id = iniciar_execucao(fabrica, TIPO, empresa_id=empresa_id, pai_id=pai_id)
    resultado = Resultado(f"empresa {id_erp}")
    leitor = _Leitor(servicos, politica, RegistroErros(fabrica, execucao_id), resultado, id_erp)

    for dia in dias:
        try:
            leitura = _ler_dia(leitor, servicos, id_erp=id_erp, dia=dia)
        except ErpApiError as exc:
            return _falhou(fabrica, execucao_id, resultado, exc)
        try:
            with fabrica() as db, db.begin():
                gravadas = _gravar_dia(
                    db,
                    empresa_id,
                    dia,
                    leitura.notas,
                    completo=leitura.completo,
                    execucao_id=execucao_id,
                    momento=agora(),
                    titulos=leitura.titulos,
                    titulos_pagos=leitura.titulos_pagos,
                    devolucoes=leitura.devolucoes,
                )
        except Exception as exc:
            logger.exception("sync.vendas.gravacao_falhou empresa=%s dia=%s", id_erp, dia)
            resultado.status = "erro"
            resultado.mensagem = f"falha ao gravar {dia}: {resumir(exc)}"
            finalizar_execucao_isolada(fabrica, execucao_id, "erro", mensagem=resultado.mensagem)
            return resultado
        if gravadas is not None:
            resultado.criados += gravadas
        elif leitura.completo:
            leitor.recusar(
                "DiaVazioPreservado",
                f"idempresa={id_erp} dia={dia}: a leitura veio sem nenhuma venda nem devolucao "
                "e o dia ja tinha vendas gravadas; mantidas ate uma leitura com dados",
                ROTA_ITENS_SAIDA,
            )

    logger.info(
        "sync.vendas.empresa empresa=%s dias=%s notas=%s", id_erp, len(dias), resultado.criados
    )
    return _fechar(fabrica, execucao_id, resultado)


def _itens_por_nota(
    leitor: _Leitor,
    servicos: ServicosErp,
    *,
    saida: bool,
    id_erp: str,
    cois: tuple[int, ...],
    dia: date,
) -> dict[str, list[ItemNota]]:
    lado, rota = ("saida", ROTA_ITENS_SAIDA) if saida else ("entrada", ROTA_ITENS_ENTRADA)
    itens_por_nota: dict[str, list[ItemNota]] = defaultdict(list)
    for coi in cois:
        pedido = f"{lado} idempresa={id_erp} idoperacao={coi} dtmovimento={dia}"
        brutos = leitor.ler(partial(servicos.pagina_itens_nota, saida, id_erp, coi, dia), pedido)
        for item in leitor.itens(brutos, pedido=pedido, endpoint=rota):
            if item.id_empresa != id_erp or item.id_operacao != coi:
                leitor.recusar(
                    "RegistroForaDoFiltro",
                    f"pedido {pedido}, veio idempresa={item.id_empresa} "
                    f"idoperacao={item.id_operacao}",
                    rota,
                )
                continue
            itens_por_nota[item.id_planilha].append(item)
    return itens_por_nota


def _ler_titulos(
    leitor: _Leitor, servicos: ServicosErp, *, id_erp: str, dia: date, pagos: bool
) -> Titulos:
    campo = "dtultimopagamento" if pagos else "dtmovimento"
    pedido = f"recebimentos idempresa={id_erp} {campo}={dia}"
    brutos = leitor.ler(
        partial(servicos.pagina_recebimentos_saida, id_erp, dia, pagos=pagos), pedido
    )
    titulos: Titulos = {}
    for bruto in brutos:
        try:
            r = mapear_recebimento(bruto, servicos.fuso)
        except RegistroInvalidoError as exc:
            leitor.recusar("RegistroInvalido", str(exc), ROTA_RECEBIMENTOS_SAIDA)
            continue
        if r.id_empresa != id_erp or r.serie != SERIE_RECEBIMENTO_VENDA:
            continue
        if r.dia_lancamento is None:
            leitor.recusar(
                "RegistroInvalido",
                f"pedido {pedido}: titulo {r.id_planilha}/{r.id_titulo} sem dtmovimento",
                ROTA_RECEBIMENTOS_SAIDA,
            )
            continue
        titulos.setdefault((r.id_planilha, r.id_titulo or "", r.parcela or ""), r)
    return titulos


def _cabecalhos(
    leitor: _Leitor,
    servicos: ServicosErp,
    *,
    saida: bool,
    id_erp: str,
    dia: date,
    itens_por_nota: dict[str, list[ItemNota]],
) -> tuple[list[tuple[Nota, list[ItemNota]]], bool]:
    rota = ROTA_NOTAS_SAIDA if saida else ROTA_NOTAS_ENTRADA
    cabecalhos: dict[str, Nota] = {}
    if saida:
        brutos = leitor.ler(
            partial(servicos.pagina_notas_emitidas, True, id_erp, dia),
            f"saida idempresa={id_erp} dtemissao={dia}",
        )
        for bruto in brutos:
            try:
                cabecalho = mapear_nota(bruto, servicos.fuso)
            except RegistroInvalidoError as exc:
                leitor.recusar("RegistroInvalido", str(exc), rota)
                continue
            if cabecalho.id_planilha in itens_por_nota and cabecalho.id_empresa == id_erp:
                cabecalhos[cabecalho.id_planilha] = cabecalho

    notas: list[tuple[Nota, list[ItemNota]]] = []
    completo = True
    for id_planilha, itens in sorted(itens_por_nota.items()):
        nota = cabecalhos.get(id_planilha)
        if nota is None:
            lado = "saida" if saida else "entrada"
            brutos = leitor.ler(
                partial(servicos.pagina_nota, saida, id_erp, id_planilha),
                f"{lado} idempresa={id_erp} idplanilha={id_planilha}",
            )
            nota = leitor.cabecalho(brutos, id_planilha=id_planilha, endpoint=rota)
        if nota is None:
            completo = False
            continue
        notas.append((nota, itens))
    return notas, completo


def _ler_dia(leitor: _Leitor, servicos: ServicosErp, *, id_erp: str, dia: date) -> LeituraDia:
    leitura = LeituraDia()
    vendas = _itens_por_nota(leitor, servicos, saida=True, id_erp=id_erp, cois=COIS_VENDA, dia=dia)
    if vendas:
        leitura.notas, leitura.completo = _cabecalhos(
            leitor, servicos, saida=True, id_erp=id_erp, dia=dia, itens_por_nota=vendas
        )
        leitura.titulos = _ler_titulos(leitor, servicos, id_erp=id_erp, dia=dia, pagos=False)
    leitura.titulos_pagos = _ler_titulos(leitor, servicos, id_erp=id_erp, dia=dia, pagos=True)
    devolucoes = _itens_por_nota(
        leitor, servicos, saida=False, id_erp=id_erp, cois=COIS_DEVOLUCAO, dia=dia
    )
    if devolucoes:
        notas, completo = _cabecalhos(
            leitor, servicos, saida=False, id_erp=id_erp, dia=dia, itens_por_nota=devolucoes
        )
        leitura.devolucoes = [(n, i) for n, i in notas if not n.cancelada]
        leitura.completo = leitura.completo and completo
    return leitura


def _soma(valores: list[Decimal | None]) -> Decimal:
    return sum((v for v in valores if v is not None), Decimal(0))


def _gravar_dia(
    db: Session,
    empresa_id: int,
    dia: date,
    notas: list[tuple[Nota, list[ItemNota]]],
    *,
    completo: bool,
    execucao_id: int | None,
    momento: datetime,
    titulos: Titulos | None = None,
    titulos_pagos: Titulos | None = None,
    devolucoes: list[tuple[Nota, list[ItemNota]]] | None = None,
) -> int | None:
    vazio = not notas and not devolucoes
    if (not completo or vazio) and _dia_tem_vendas(db, empresa_id, dia):
        return None
    ids = [nota.id_planilha for nota, _ in notas]
    filtro = Venda.data_venda == dia
    if ids:
        filtro = or_(filtro, Venda.id_erp.in_(ids))
    db.execute(delete(Venda).where(Venda.empresa_id == empresa_id, filtro))

    for nota, itens in notas:
        coi = next((i.id_operacao for i in itens if i.id_operacao in CANAIS), COIS_VENDA[0])
        vendedores = [i.id_vendedor for i in itens if i.id_vendedor]
        db.add(
            Venda(
                empresa_id=empresa_id,
                id_erp=nota.id_planilha,
                numero_nota=nota.numero,
                serie=nota.serie,
                modelo=nota.modelo,
                coi=coi,
                canal=CANAIS[coi],
                data_venda=dia,
                momento=nota.data_movimento or nota.data_emissao,
                cancelada=nota.cancelada,
                valor_total=_soma([i.valor_liquido for i in itens]),
                valor_desconto=_soma([i.valor_desconto for i in itens]),
                quantidade_itens=len(itens),
                id_vendedor=vendedores[0] if vendedores else None,
                sincronizado_em=momento,
                itens=[
                    VendaItem(
                        sequencia=i.sequencia,
                        id_produto=i.id_produto,
                        id_subproduto=i.id_subproduto,
                        descricao_produto=i.descricao_produto,
                        cfop=i.cfop,
                        quantidade=i.quantidade,
                        valor_liquido=i.valor_liquido,
                        valor_desconto=i.valor_desconto,
                    )
                    for i in itens
                ],
            )
        )

    _gravar_titulos(db, empresa_id, dia, titulos or {}, titulos_pagos or {})

    devolvidas = devolucoes or []
    ids_devolucao = [nota.id_planilha for nota, _ in devolvidas]
    filtro_devolucao = Devolucao.data_devolucao == dia
    if ids_devolucao:
        filtro_devolucao = or_(filtro_devolucao, Devolucao.id_erp.in_(ids_devolucao))
    db.execute(delete(Devolucao).where(Devolucao.empresa_id == empresa_id, filtro_devolucao))
    for nota, itens in devolvidas:
        db.add(
            Devolucao(
                empresa_id=empresa_id,
                id_erp=nota.id_planilha,
                numero_nota=nota.numero,
                coi=next((i.id_operacao for i in itens if i.id_operacao), COIS_DEVOLUCAO[0]),
                data_devolucao=dia,
                valor_total=_soma([i.valor_liquido for i in itens]),
                quantidade_itens=len(itens),
                sincronizado_em=momento,
            )
        )

    if completo:
        valores = {
            "notas": len(notas),
            "versao": VERSAO_DIA,
            "sincronizado_em": momento,
            "sincronizacao_id": execucao_id,
        }
        db.execute(
            insert(VendaDia)
            .values(empresa_id=empresa_id, dia=dia, **valores)
            .on_conflict_do_update(index_elements=["empresa_id", "dia"], set_=valores)
        )
    return len(notas)


def _linha_titulo(
    empresa_id: int, chave: tuple[str, str, str], t: Recebimento
) -> dict[str, object]:
    id_planilha, id_titulo, parcela = chave
    valor = t.valor or Decimal(0)
    pago = t.valor_pago or Decimal(0)
    pendente = t.valor_pendente
    return {
        "empresa_id": empresa_id,
        "id_planilha": id_planilha,
        "id_titulo": id_titulo,
        "parcela": parcela,
        "id_forma": t.id_forma or 0,
        "forma": t.forma or "NAO INFORMADA",
        "dia_lancamento": t.dia_lancamento,
        "vencimento": t.vencimento,
        "dia_pagamento": t.dia_pagamento if pago else None,
        "valor": valor,
        "valor_pago": pago,
        "valor_pendente": pendente if pendente is not None else max(valor - pago, Decimal(0)),
        "juros": t.juros or Decimal(0),
        "desconto": t.desconto or Decimal(0),
    }


_CHAVE_TITULO = ("empresa_id", "id_planilha", "id_titulo", "parcela")


def _gravar_titulos(
    db: Session, empresa_id: int, dia: date, lancados: Titulos, pagos: Titulos
) -> None:
    db.execute(
        delete(VendaTitulo).where(
            VendaTitulo.empresa_id == empresa_id, VendaTitulo.dia_lancamento == dia
        )
    )
    if pagos:
        chave = tuple_(VendaTitulo.id_planilha, VendaTitulo.id_titulo, VendaTitulo.parcela)
        db.execute(
            update(VendaTitulo)
            .where(
                VendaTitulo.empresa_id == empresa_id,
                VendaTitulo.dia_pagamento == dia,
                chave.not_in(list(pagos)),
            )
            .values(dia_pagamento=None, valor_pago=0, valor_pendente=VendaTitulo.valor)
            .execution_options(synchronize_session=False)
        )

    linhas = [_linha_titulo(empresa_id, c, t) for c, t in {**pagos, **lancados}.items()]
    for inicio in range(0, len(linhas), TITULOS_POR_INSERT):
        lote = insert(VendaTitulo).values(linhas[inicio : inicio + TITULOS_POR_INSERT])
        db.execute(
            lote.on_conflict_do_update(
                index_elements=list(_CHAVE_TITULO),
                set_={c: lote.excluded[c] for c in linhas[0] if c not in _CHAVE_TITULO},
            )
        )


def _dia_tem_vendas(db: Session, empresa_id: int, dia: date) -> bool:
    venda = exists().where(Venda.empresa_id == empresa_id, Venda.data_venda == dia)
    devolucao = exists().where(Devolucao.empresa_id == empresa_id, Devolucao.data_devolucao == dia)
    return bool(db.scalar(select(or_(venda, devolucao))))
