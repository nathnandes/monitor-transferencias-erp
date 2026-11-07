from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Any

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import Empresa, MovimentoEstoque, MovimentoEstoqueDia, NotaMovimento
from app.dominio.empresa_errada import eh_empresa_errada
from app.dominio.operacoes_estoque import CATALOGO, VERSAO_LIVRO, operacao
from app.erp.errors import ErpApiError
from app.erp.schemas import RespostaPaginada
from app.erp.servicos import (
    ROTA_ITENS_ENTRADA,
    ROTA_ITENS_SAIDA,
    ItemNota,
    Nota,
    RegistroInvalidoError,
    ServicosErp,
    mapear_nota,
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

TIPO = "movimentos_estoque"

VERSAO_DIA = VERSAO_LIVRO


_MAX_COIS_POR_DIA = 200


COIS_SEM_CABECALHO = frozenset({80, 8080, 2000})

_MIN_CABECALHOS_EM_LOTE = 20

_MAX_CABECALHOS_UM_A_UM = 300

_MAX_FORNECEDORES_POR_EXECUCAO = 200

COIS_COMPRA = tuple(
    sorted(c for (saida, c), o in CATALOGO.items() if not saida and o.categoria == "compra")
)

Relogio = Callable[[], datetime]


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
        MovimentoEstoqueDia,
        empresa_id,
        versao=VERSAO_DIA,
        hoje=hoje,
        janela_dias=janela_dias,
        historico_dias=historico_dias,
        dias_por_ciclo=dias_por_ciclo,
    )


def sincronizar_movimentos(
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
        modelo_dia=MovimentoEstoqueDia,
        versao=VERSAO_DIA,
        sincronizar_empresa=sincronizar_movimentos_empresa,
        ambiente=ambiente,
        empresas=empresas,
        politica=politica,
        janela_dias=janela_dias,
        historico_dias=historico_dias,
        dias_por_ciclo=dias_por_ciclo,
        agora=agora,
    )


def sincronizar_movimentos_empresa(
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
        ignorados_antes = resultado.ignorados
        try:
            itens = _ler_dia(leitor, servicos, id_erp=id_erp, dia=dia)
        except ErpApiError as exc:
            return _falhou(fabrica, execucao_id, resultado, exc)
        completo = resultado.ignorados == ignorados_antes
        with fabrica() as db:
            pendentes = _sem_cabecalho(db, empresa_id, itens)
        cabecalhos = _ler_cabecalhos(leitor, servicos, id_erp=id_erp, dia=dia, pendentes=pendentes)
        try:
            with fabrica() as db, db.begin():
                momento = agora()
                gravou = _gravar_dia(
                    db,
                    empresa_id,
                    dia,
                    itens,
                    completo=completo,
                    execucao_id=execucao_id,
                    momento=momento,
                )
                _gravar_cabecalhos(db, empresa_id, cabecalhos, momento=momento)
        except Exception as exc:
            logger.exception("sync.movimentos.gravacao_falhou empresa=%s dia=%s", id_erp, dia)
            resultado.status = "erro"
            resultado.mensagem = f"falha ao gravar {dia}: {resumir(exc)}"
            finalizar_execucao_isolada(fabrica, execucao_id, "erro", mensagem=resultado.mensagem)
            return resultado
        if gravou:
            resultado.criados += len(itens)
        elif completo:
            leitor.recusar(
                "DiaVazioPreservado",
                f"idempresa={id_erp} dtmovimento={dia}: a leitura veio sem nenhum item e o dia "
                "ja tinha movimentos gravados; mantidos ate uma leitura com dados",
                ROTA_ITENS_SAIDA,
            )

    fornecedores = _completar_fornecedores(
        fabrica, leitor, servicos, empresa_id=empresa_id, id_erp=id_erp, agora=agora
    )
    logger.info(
        "sync.movimentos.empresa empresa=%s dias=%s movimentos=%s fornecedores=%s",
        id_erp,
        len(dias),
        resultado.criados,
        fornecedores,
    )
    return _fechar(fabrica, execucao_id, resultado)


def _consultar(
    leitor: _Leitor, servicos: ServicosErp, *, saida: bool, id_erp: str, dia: date, acima_de: int
) -> RespostaPaginada:
    lado = "saida" if saida else "entrada"
    pedido = f"{lado} idempresa={id_erp} dtmovimento={dia} idoperacao>{acima_de}"

    def ao_falhar(exc: ErpApiError, tentativa: int) -> None:
        leitor.erros.erpapi(exc, tentativa=tentativa, id_empresa=id_erp, pedido=pedido)

    resposta = com_retry(
        partial(servicos.pagina_itens_dia, saida, id_erp, dia, acima_de, 1),
        leitor.politica,
        ao_falhar,
    )
    leitor.resultado.paginas += 1
    return resposta


def _cois_fora_do_catalogo(
    leitor: _Leitor, servicos: ServicosErp, *, saida: bool, id_erp: str, dia: date
) -> list[int]:
    achados: list[int] = []
    acima_de = -1
    for _ in range(_MAX_COIS_POR_DIA):
        resposta = _consultar(
            leitor, servicos, saida=saida, id_erp=id_erp, dia=dia, acima_de=acima_de
        )
        cois = {int(r["idoperacao"]) for r in resposta.registros if r.get("idoperacao")}
        if not cois:
            break
        achados += [c for c in cois if (saida, c) not in CATALOGO and c not in achados]
        acima_de = min(cois)
    return sorted(achados)


def _ler_coi(
    leitor: _Leitor,
    servicos: ServicosErp,
    *,
    saida: bool,
    id_erp: str,
    dia: date,
    coi: int,
    itens: list[tuple[bool, ItemNota]],
) -> int:
    lado, rota = ("saida", ROTA_ITENS_SAIDA) if saida else ("entrada", ROTA_ITENS_ENTRADA)
    pedido = f"{lado} idempresa={id_erp} idoperacao={coi} dtmovimento={dia}"
    brutos = leitor.ler(partial(servicos.pagina_itens_nota, saida, id_erp, coi, dia), pedido)
    for item in leitor.itens(brutos, pedido=pedido, endpoint=rota):
        if item.id_empresa != id_erp or item.id_operacao != coi:
            leitor.recusar(
                "RegistroForaDoFiltro",
                f"pedido {pedido}, veio idempresa={item.id_empresa} idoperacao={item.id_operacao}",
                rota,
            )
            continue
        itens.append((saida, item))
    return len(brutos)


def _ler_dia(
    leitor: _Leitor, servicos: ServicosErp, *, id_erp: str, dia: date
) -> list[tuple[bool, ItemNota]]:
    itens: list[tuple[bool, ItemNota]] = []
    for saida in (True, False):
        lado, rota = ("saida", ROTA_ITENS_SAIDA) if saida else ("entrada", ROTA_ITENS_ENTRADA)
        total = _consultar(leitor, servicos, saida=saida, id_erp=id_erp, dia=dia, acima_de=-1).total
        if total == 0:
            continue
        cois = sorted(c for lado_coi, c in CATALOGO if lado_coi == saida)
        lidos = sum(
            _ler_coi(leitor, servicos, saida=saida, id_erp=id_erp, dia=dia, coi=c, itens=itens)
            for c in cois
        )
        if total is not None and lidos < total:
            novos = _cois_fora_do_catalogo(leitor, servicos, saida=saida, id_erp=id_erp, dia=dia)
            lidos += sum(
                _ler_coi(leitor, servicos, saida=saida, id_erp=id_erp, dia=dia, coi=c, itens=itens)
                for c in novos
            )
            cois += novos
        if total is not None and lidos != total:
            leitor.recusar(
                "LivroIncompleto",
                f"{lado} idempresa={id_erp} dtmovimento={dia}: {total} itens no dia, "
                f"{lidos} lidos nos COIs do catalogo e nos novos achados",
                rota,
            )
    return itens


def _sem_cabecalho(
    db: Session, empresa_id: int, itens: list[tuple[bool, ItemNota]]
) -> dict[str, bool]:
    documentos = {
        i.id_planilha: saida for saida, i in itens if i.id_operacao not in COIS_SEM_CABECALHO
    }
    if not documentos:
        return {}
    categorias: dict[str, set[str]] = {}
    for saida, i in itens:
        if i.id_operacao is not None:
            categoria = operacao(saida, i.id_operacao).categoria
            categorias.setdefault(i.id_planilha, set()).add(categoria)
    grupo = {
        cnpj: id_
        for cnpj, id_ in db.execute(
            select(Empresa.cnpj, Empresa.id).where(Empresa.cnpj.is_not(None))
        )
    }
    gravados = db.execute(
        select(
            NotaMovimento.id_planilha,
            NotaMovimento.encontrado,
            NotaMovimento.destinatario_lido,
            NotaMovimento.emitente_lido,
            NotaMovimento.cnpj_destinatario,
            NotaMovimento.cancelada,
        ).where(
            NotaMovimento.empresa_id == empresa_id,
            NotaMovimento.id_planilha.in_(documentos),
        )
    ).all()

    def reler(g: Any) -> bool:
        if not g.encontrado:
            return False
        if not documentos[g.id_planilha]:
            return not g.emitente_lido
        return not g.destinatario_lido or eh_empresa_errada(
            empresa_id=empresa_id,
            destino_id=grupo.get(g.cnpj_destinatario or ""),
            cancelada=g.cancelada,
            categoria=max(categorias.get(g.id_planilha) or {""}),
        )

    em_dia = {g.id_planilha for g in gravados if not reler(g)}
    return {p: saida for p, saida in documentos.items() if p not in em_dia}


def _mapear_cabecalhos(
    servicos: ServicosErp, brutos: list[dict[str, object]], id_erp: str
) -> dict[str, Nota]:
    notas: dict[str, Nota] = {}
    for bruto in brutos:
        try:
            nota = mapear_nota(bruto, servicos.fuso)
        except RegistroInvalidoError as exc:
            logger.warning("sync.movimentos.cabecalho_invalido empresa=%s: %s", id_erp, exc)
            continue
        if nota.id_empresa == id_erp:
            notas[nota.id_planilha] = nota
    return notas


def _ler_cabecalhos(
    leitor: _Leitor,
    servicos: ServicosErp,
    *,
    id_erp: str,
    dia: date,
    pendentes: dict[str, bool],
) -> list[tuple[str, bool, Nota | None]]:
    lidos: list[tuple[str, bool, Nota | None]] = []
    try:
        for saida in (True, False):
            faltam = sorted(p for p, s in pendentes.items() if s == saida)
            achados: dict[str, Nota] = {}
            lado = "saida" if saida else "entrada"
            if saida and len(faltam) > _MIN_CABECALHOS_EM_LOTE:
                brutos = leitor.ler(
                    partial(servicos.pagina_notas_emitidas, True, id_erp, dia),
                    f"saida idempresa={id_erp} dtemissao={dia}",
                )
                achados = _mapear_cabecalhos(servicos, brutos, id_erp)
            lidos += [(p, saida, achados[p]) for p in faltam if p in achados]
            um_a_um = [p for p in faltam if p not in achados][:_MAX_CABECALHOS_UM_A_UM]
            for id_planilha in um_a_um:
                brutos = leitor.ler(
                    partial(servicos.pagina_nota, saida, id_erp, id_planilha),
                    f"{lado} idempresa={id_erp} idplanilha={id_planilha}",
                )
                nota = _mapear_cabecalhos(servicos, brutos, id_erp).get(id_planilha)
                lidos.append((id_planilha, saida, nota))
    except ErpApiError as exc:
        logger.warning(
            "sync.movimentos.cabecalhos_falharam empresa=%s dia=%s: %s", id_erp, dia, exc
        )
    return lidos


def _gravar_cabecalhos(
    db: Session,
    empresa_id: int,
    cabecalhos: list[tuple[str, bool, Nota | None]],
    *,
    momento: datetime,
) -> None:
    for id_planilha, saida, nota in cabecalhos:
        valores = {
            "saida": saida,
            "encontrado": nota is not None,
            "numero": nota.numero if nota else None,
            "momento": nota.data_movimento if nota else None,
            "usuario": nota.usuario if nota else None,
            "cnpj_destinatario": nota.cnpj_cpf if nota and saida else None,
            "nome_destinatario": nota.nome if nota and saida else None,
            "cnpj_emitente": nota.cnpj_cpf if nota and not saida else None,
            "nome_emitente": nota.nome if nota and not saida else None,
            "cancelada": nota.cancelada if nota else None,
            "destinatario_lido": True,
            "emitente_lido": True,
            "sincronizado_em": momento,
        }
        db.execute(
            insert(NotaMovimento)
            .values(empresa_id=empresa_id, id_planilha=id_planilha, **valores)
            .on_conflict_do_update(index_elements=["empresa_id", "id_planilha"], set_=valores)
        )


def _compras_sem_emitente(db: Session, empresa_id: int, limite: int) -> list[str]:
    m, n = MovimentoEstoque, NotaMovimento
    return list(
        db.scalars(
            select(m.id_planilha)
            .outerjoin(n, (n.empresa_id == m.empresa_id) & (n.id_planilha == m.id_planilha))
            .where(
                m.coi.in_(COIS_COMPRA),
                m.empresa_id == empresa_id,
                m.tipo == "compra",
                or_(
                    n.id_planilha.is_(None),
                    n.encontrado.is_(True) & n.emitente_lido.is_(False),
                ),
            )
            .group_by(m.id_planilha)
            .order_by(func.max(m.dia).desc(), m.id_planilha)
            .limit(limite)
        )
    )


def _completar_fornecedores(
    fabrica: FabricaSessao,
    leitor: _Leitor,
    servicos: ServicosErp,
    *,
    empresa_id: int,
    id_erp: str,
    agora: Relogio,
) -> int:
    with fabrica() as db:
        pendentes = _compras_sem_emitente(db, empresa_id, _MAX_FORNECEDORES_POR_EXECUCAO)
    lidos: list[tuple[str, bool, Nota | None]] = []
    try:
        for id_planilha in pendentes:
            brutos = leitor.ler(
                partial(servicos.pagina_nota, False, id_erp, id_planilha),
                f"entrada idempresa={id_erp} idplanilha={id_planilha}",
            )
            lidos.append(
                (id_planilha, False, _mapear_cabecalhos(servicos, brutos, id_erp).get(id_planilha))
            )
    except ErpApiError as exc:
        logger.warning("sync.movimentos.fornecedores_falharam empresa=%s: %s", id_erp, exc)
    if lidos:
        with fabrica() as db, db.begin():
            _gravar_cabecalhos(db, empresa_id, lidos, momento=agora())
    return len(lidos)


def _efeito(valor: Decimal | None, saida: bool, coi: int) -> Decimal | None:
    return None if valor is None else valor * operacao(saida, coi).fator


def _gravar_dia(
    db: Session,
    empresa_id: int,
    dia: date,
    itens: list[tuple[bool, ItemNota]],
    *,
    completo: bool,
    execucao_id: int | None,
    momento: datetime,
) -> bool:
    if (not completo or not itens) and _dia_tem_movimentos(db, empresa_id, dia):
        return False
    db.execute(
        delete(MovimentoEstoque).where(
            MovimentoEstoque.empresa_id == empresa_id, MovimentoEstoque.dia == dia
        )
    )
    db.add_all(
        MovimentoEstoque(
            empresa_id=empresa_id,
            dia=dia,
            coi=i.id_operacao,
            tipo=operacao(saida, i.id_operacao).categoria,
            operacao=i.descricao_operacao,
            id_planilha=i.id_planilha,
            sequencia=i.sequencia,
            id_produto=i.id_produto,
            id_subproduto=i.id_subproduto or i.id_produto,
            descricao_produto=i.descricao_produto,
            quantidade=_efeito(i.quantidade, saida, i.id_operacao),
            valor=_efeito(i.valor_liquido, saida, i.id_operacao),
            sincronizado_em=momento,
        )
        for saida, i in itens
        if i.id_operacao is not None
    )
    if not completo:
        return True
    valores = {
        "movimentos": len(itens),
        "versao": VERSAO_DIA,
        "sincronizado_em": momento,
        "sincronizacao_id": execucao_id,
    }
    db.execute(
        insert(MovimentoEstoqueDia)
        .values(empresa_id=empresa_id, dia=dia, **valores)
        .on_conflict_do_update(index_elements=["empresa_id", "dia"], set_=valores)
    )
    return True


def _dia_tem_movimentos(db: Session, empresa_id: int, dia: date) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    MovimentoEstoque.empresa_id == empresa_id, MovimentoEstoque.dia == dia
                )
            )
        )
    )
