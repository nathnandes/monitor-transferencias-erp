from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Integer, delete, distinct, func, literal, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import ScalarResult
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.locais_perda import fora_da_perda
from app.database.models import Empresa, EstoqueConsolidado, EstoqueEmpresaLocalLote
from app.erp.errors import ErpApiError
from app.erp.servicos import (
    CAMPO_FILTRO_EMPRESA,
    ROTA_SALDO_ESTOQUE_EMPRESA,
    Filtros,
    RegistroInvalidoError,
    SaldoEstoque,
    ServicosErp,
    descrever,
    mapear_saldo,
)
from app.sync.comum import (
    FabricaSessao,
    FalhaGeralError,
    Leitura,
    PoliticaRetry,
    RegistroErros,
    agora_utc,
    com_retry,
    eh_falha_geral,
    finalizar_execucao,
    finalizar_execucao_isolada,
    iniciar_execucao,
    limitar_cursor,
    percorrer_paginas,
    resumir,
)
from app.sync.empresas import ResultadoSincronizacao

logger = get_logger(__name__)

TIPO = "estoque"
TIPO_COMPLETO = "estoque_completo"


MARGEM_INCREMENTAL = timedelta(minutes=10)

AUSENCIAS_PARA_DESATIVAR = 2


MAX_PRODUTOS_RESERVA = 200

_LOTE_UPSERT = 1000
_MAX_ERROS_DE_REGISTRO = 5

Relogio = Callable[[], datetime]
Chave = tuple[str, str, str, str]


@dataclass
class ResultadoEmpresa:
    id_erp: str
    status: str
    completa: bool = False
    paginas: int = 0
    recebidos: int = 0
    criados: int = 0
    atualizados: int = 0
    ignorados: int = 0
    ausentes: int = 0
    desativados: int = 0
    mensagem: str | None = None


@dataclass
class _Traducao:
    saldos: dict[Chave, SaldoEstoque] = field(default_factory=dict)
    invalidos: int = 0
    de_outra_empresa: int = 0
    duplicados: int = 0

    detalhados: int = 0
    sem_detalhe: int = 0

    @property
    def ignorados(self) -> int:
        return self.invalidos + self.de_outra_empresa + self.duplicados


@dataclass
class _Estado:
    ultima_alteracao: datetime | None
    com_reserva: set[Chave]


def sincronizar_estoque(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    ambiente: str,
    empresas: tuple[str, ...],
    politica: PoliticaRetry,
    completa: bool = False,
    agora: Relogio = agora_utc,
) -> ResultadoSincronizacao:
    tipo = TIPO_COMPLETO if completa else TIPO
    pai_id = iniciar_execucao(fabrica, tipo)
    erros = RegistroErros(fabrica, pai_id)

    with fabrica() as db:
        cadastradas = {
            id_erp: empresa_id
            for empresa_id, id_erp in db.execute(
                select(Empresa.id, Empresa.id_erp).where(
                    Empresa.ambiente == ambiente, Empresa.id_erp.in_(empresas)
                )
            )
        }
    nao_cadastradas = [e for e in empresas if e not in cadastradas]
    for id_erp in nao_cadastradas:
        erros.outro(
            "EmpresaNaoCadastrada",
            f"empresa {id_erp} nao esta na tabela empresas ({ambiente}); "
            "rode a sincronizacao de empresas antes",
            id_empresa=id_erp,
        )

    resultados: list[ResultadoEmpresa] = []
    interrupcao: str | None = None
    try:
        com_retry(servicos.autenticar, politica, lambda exc, t: erros.erpapi(exc, tentativa=t))
        for id_erp in empresas:
            if id_erp not in cadastradas:
                continue
            resultados.append(
                sincronizar_estoque_empresa(
                    fabrica,
                    servicos,
                    empresa_id=cadastradas[id_erp],
                    id_erp=id_erp,
                    pai_id=pai_id,
                    politica=politica,
                    completa=completa,
                    agora=agora,
                )
            )
    except FalhaGeralError as exc:
        interrupcao = f"interrompida: {exc}"
    except ErpApiError as exc:
        interrupcao = f"interrompida: {resumir(exc)}"
    except Exception as exc:
        logger.exception("sync.estoque.falha_interna execucao=%s", pai_id)
        finalizar_execucao_isolada(fabrica, pai_id, "erro", mensagem=resumir(exc))
        raise

    ok = [r for r in resultados if r.status != "erro"]
    mensagens: list[str] = []
    if interrupcao:
        mensagens.append(interrupcao)
    if nao_cadastradas:
        mensagens.append(f"empresas nao cadastradas: {', '.join(nao_cadastradas)}")
    mensagens += [f"empresa {r.id_erp}: {r.mensagem}" for r in resultados if r.mensagem]

    if ok:
        try:
            produtos = recalcular_estoque_consolidado(
                fabrica, ambiente=ambiente, empresas=empresas, agora=agora
            )
            logger.info("sync.estoque.consolidado execucao=%s produtos=%s", pai_id, produtos)
        except Exception as exc:
            logger.exception("sync.estoque.consolidado_falhou execucao=%s", pai_id)
            mensagens.insert(0, f"consolidado nao recalculado: {resumir(exc)}")
            ok = []

    if interrupcao or not ok:
        status = "erro"
    elif len(ok) == len(empresas) and all(r.status == "sucesso" for r in ok):
        status = "sucesso"
    else:
        status = "parcial"

    mensagem = "; ".join(mensagens) or None
    finalizar_execucao_isolada(
        fabrica,
        pai_id,
        status,
        mensagem=mensagem,
        empresas_processadas=len(ok),
        paginas_processadas=sum(r.paginas for r in resultados),
        registros_consultados=sum(r.recebidos for r in resultados),
        registros_criados=sum(r.criados for r in resultados),
        registros_atualizados=sum(r.atualizados for r in resultados),
        registros_ignorados=sum(r.ignorados for r in resultados),
    )
    logger.info(
        "sync.estoque.fim tipo=%s execucao=%s status=%s empresas_ok=%s/%s",
        tipo,
        pai_id,
        status,
        len(ok),
        len(empresas),
    )
    return ResultadoSincronizacao(pai_id, status, mensagem)


def sincronizar_estoque_empresa(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    empresa_id: int,
    id_erp: str,
    pai_id: int | None,
    politica: PoliticaRetry,
    completa: bool = False,
    agora: Relogio = agora_utc,
) -> ResultadoEmpresa:
    execucao_id = iniciar_execucao(
        fabrica, TIPO_COMPLETO if completa else TIPO, empresa_id=empresa_id, pai_id=pai_id
    )
    erros = RegistroErros(fabrica, execucao_id)
    leitura = Leitura()
    traducao = _Traducao()

    estado = None if completa else _estado(fabrica, empresa_id)
    if estado is not None:
        estado.ultima_alteracao = limitar_cursor(
            estado.ultima_alteracao, agora(), f"estoque empresa={id_erp}"
        )

    le_tudo = estado is None or estado.ultima_alteracao is None

    def _ler(filtros: Filtros) -> None:
        inicio = len(leitura.registros)
        pedido = f"{CAMPO_FILTRO_EMPRESA} IGUAL {id_erp}"
        if filtros:
            pedido += f", {descrever(filtros)}"
        percorrer_paginas(
            lambda pagina: servicos.pagina_saldo_estoque(id_erp, pagina, filtros),
            max_paginas=servicos.max_paginas,
            politica=politica,
            ao_falhar=lambda exc, tentativa, pagina: erros.erpapi(
                exc,
                tentativa=tentativa,
                id_empresa=id_erp,
                pedido=f"page={pagina}, clausulas=[{pedido}]",
            ),
            leitura=leitura,
        )
        _traduzir(
            leitura.registros[inicio:],
            id_erp,
            erros,
            traducao,
            servicos,
            contar_duplicados=le_tudo,
        )

    try:
        if le_tudo:
            _ler(())
        else:
            assert estado is not None and estado.ultima_alteracao is not None
            _ler(servicos.filtro_alterado_desde(estado.ultima_alteracao - MARGEM_INCREMENTAL))
            _ler(servicos.filtro_com_reserva())
            liberadas = estado.com_reserva - traducao.saldos.keys()
            produtos = sorted({(c[0], c[1]) for c in liberadas})
            if len(produtos) > MAX_PRODUTOS_RESERVA:
                logger.warning(
                    "sync.estoque.reservas_adiadas empresa=%s produtos=%s",
                    id_erp,
                    len(produtos) - MAX_PRODUTOS_RESERVA,
                )
            for id_produto, id_subproduto in produtos[:MAX_PRODUTOS_RESERVA]:
                _ler(servicos.filtro_produto(id_produto, id_subproduto))
    except ErpApiError as exc:
        mensagem = resumir(exc)
        finalizar_execucao_isolada(
            fabrica,
            execucao_id,
            "erro",
            mensagem=mensagem,
            paginas_processadas=leitura.paginas,
            registros_consultados=len(leitura.registros),
        )
        if eh_falha_geral(exc):
            raise FalhaGeralError(exc) from None
        return ResultadoEmpresa(
            id_erp,
            "erro",
            completa=le_tudo,
            paginas=leitura.paginas,
            recebidos=len(leitura.registros),
            mensagem=mensagem,
        )
    _resumir_sem_detalhe(traducao, erros, id_erp)

    resultado = ResultadoEmpresa(
        id_erp,
        "sucesso",
        completa=le_tudo,
        paginas=leitura.paginas,
        recebidos=len(leitura.registros),
        ignorados=traducao.ignorados,
    )

    if le_tudo and not traducao.saldos:
        resultado.status = "erro"
        resultado.mensagem = (
            f"nenhum registro valido em {len(leitura.registros)} recebido(s); "
            "estoque anterior mantido"
        )
        finalizar_execucao_isolada(
            fabrica,
            execucao_id,
            "erro",
            mensagem=resultado.mensagem,
            paginas_processadas=resultado.paginas,
            registros_consultados=resultado.recebidos,
            registros_ignorados=resultado.ignorados,
        )
        return resultado

    leitura_confiavel = (
        traducao.invalidos == 0 and traducao.de_outra_empresa == 0 and traducao.duplicados == 0
    )
    conta_ausencias = completa and leitura_confiavel
    if traducao.ignorados:
        resultado.status = "parcial"
        partes = [
            f"{n} {rotulo}"
            for n, rotulo in (
                (traducao.invalidos, "invalido(s)"),
                (traducao.de_outra_empresa, "de outra empresa"),
                (traducao.duplicados, "duplicado(s)"),
            )
            if n
        ]
        resultado.mensagem = "registros ignorados: " + ", ".join(partes)
        if completa and not leitura_confiavel:
            resultado.mensagem += "; ausencias nao foram contadas"

    try:
        with fabrica() as db, db.begin():
            momento = agora()
            resultado.criados, resultado.atualizados = _gravar(
                db, empresa_id, execucao_id, traducao.saldos.values(), momento
            )
            if conta_ausencias:
                resultado.ausentes, resultado.desativados = _contar_ausencias(
                    db, empresa_id, execucao_id, momento
                )
            finalizar_execucao(
                db,
                execucao_id,
                resultado.status,
                mensagem=resultado.mensagem,
                empresas_processadas=1,
                paginas_processadas=resultado.paginas,
                registros_consultados=resultado.recebidos,
                registros_criados=resultado.criados,
                registros_atualizados=resultado.atualizados,
                registros_ignorados=resultado.ignorados,
            )
    except Exception as exc:
        logger.exception("sync.estoque.gravacao_falhou empresa=%s", id_erp)
        resultado.status = "erro"
        resultado.mensagem = f"falha ao gravar: {resumir(exc)}"
        resultado.criados = resultado.atualizados = 0
        resultado.ausentes = resultado.desativados = 0
        finalizar_execucao_isolada(fabrica, execucao_id, "erro", mensagem=resultado.mensagem)
        return resultado

    logger.info(
        "sync.estoque.empresa empresa=%s modo=%s status=%s paginas=%s recebidos=%s "
        "criados=%s atualizados=%s ignorados=%s ausentes=%s desativados=%s",
        id_erp,
        "completa" if le_tudo else "incremental",
        resultado.status,
        resultado.paginas,
        resultado.recebidos,
        resultado.criados,
        resultado.atualizados,
        resultado.ignorados,
        resultado.ausentes,
        resultado.desativados,
    )
    return resultado


def _estado(fabrica: FabricaSessao, empresa_id: int) -> _Estado:
    e = EstoqueEmpresaLocalLote
    with fabrica() as db:
        ultima = db.scalar(select(func.max(e.data_alteracao_erp)).where(e.empresa_id == empresa_id))
        com_reserva: set[Chave] = {
            (p, s, loc, lote)
            for p, s, loc, lote in db.execute(
                select(e.id_produto, e.id_subproduto, e.id_local_estoque, e.descricao_lote).where(
                    e.empresa_id == empresa_id, e.ativo.is_(True), e.saldo_reservado > 0
                )
            )
        }
    return _Estado(ultima, com_reserva)


def _traduzir(
    registros: list[dict[str, Any]],
    id_erp: str,
    erros: RegistroErros,
    traducao: _Traducao,
    servicos: ServicosErp,
    *,
    contar_duplicados: bool,
) -> None:
    def _recusar(tipo: str, mensagem: str) -> None:
        if traducao.detalhados < _MAX_ERROS_DE_REGISTRO:
            traducao.detalhados += 1
            erros.outro(tipo, mensagem, id_empresa=id_erp, endpoint=ROTA_SALDO_ESTOQUE_EMPRESA)
        else:
            traducao.sem_detalhe += 1

    for bruto in registros:
        try:
            saldo = mapear_saldo(bruto, servicos.fuso)
        except RegistroInvalidoError as exc:
            traducao.invalidos += 1
            _recusar("RegistroInvalido", str(exc))
            continue
        if saldo.id_empresa != id_erp:
            traducao.de_outra_empresa += 1
            _recusar(
                "RegistroDeOutraEmpresa",
                f"pedido idempresa={id_erp}, veio idempresa={saldo.id_empresa}",
            )
            continue
        if contar_duplicados and saldo.chave in traducao.saldos:
            traducao.duplicados += 1
        traducao.saldos[saldo.chave] = saldo


def _resumir_sem_detalhe(traducao: _Traducao, erros: RegistroErros, id_erp: str) -> None:
    if traducao.sem_detalhe:
        erros.outro(
            "RegistrosIgnorados",
            f"{traducao.sem_detalhe} outro(s) registro(s) ignorado(s) sem detalhe individual",
            id_empresa=id_erp,
            endpoint=ROTA_SALDO_ESTOQUE_EMPRESA,
        )


_ATUALIZAVEIS = (
    "descricao_local_estoque",
    "utiliza_lote",
    "permite_estoque_negativo",
    "saldo_atual",
    "saldo_reservado",
    "saldo_disponivel",
    "data_alteracao_erp",
    "inativo_erp",
    "sincronizado_em",
    "ultima_sincronizacao_id",
)


def _linha(empresa_id: int, execucao_id: int, s: SaldoEstoque, momento: datetime) -> dict[str, Any]:
    return {
        "empresa_id": empresa_id,
        "id_produto": s.id_produto,
        "id_subproduto": s.id_subproduto,
        "id_local_estoque": s.id_local_estoque,
        "descricao_local_estoque": s.descricao_local_estoque,
        "utiliza_lote": s.utiliza_lote,
        "descricao_lote": s.descricao_lote,
        "permite_estoque_negativo": s.permite_estoque_negativo,
        "saldo_atual": s.saldo_atual,
        "saldo_reservado": s.saldo_reservado,
        "saldo_disponivel": s.saldo_disponivel,
        "data_alteracao_erp": s.data_alteracao,
        "inativo_erp": s.inativo_erp,
        "ativo": True,
        "ausencias_leitura_completa": 0,
        "sincronizado_em": momento,
        "ultima_sincronizacao_id": execucao_id,
    }


def _gravar(
    db: Session,
    empresa_id: int,
    execucao_id: int,
    saldos: Iterable[SaldoEstoque],
    momento: datetime,
) -> tuple[int, int]:
    linhas = [_linha(empresa_id, execucao_id, s, momento) for s in saldos]
    criados = 0
    for inicio in range(0, len(linhas), _LOTE_UPSERT):
        valores = insert(EstoqueEmpresaLocalLote).values(linhas[inicio : inicio + _LOTE_UPSERT])
        upsert = valores.on_conflict_do_update(
            constraint="uq_estoque_empresa_local_lote_chave",
            set_={
                **{c: valores.excluded[c] for c in _ATUALIZAVEIS},
                "ativo": True,
                "ausencias_leitura_completa": 0,
                "removido_em": None,
                "updated_at": func.now(),
            },
        )
        novos: ScalarResult[bool] = db.scalars(
            upsert.returning(literal_column("(xmax = 0)").label("criado"))
        )
        criados += sum(1 for criado in novos if criado)
    return criados, len(linhas) - criados


def _contar_ausencias(
    db: Session, empresa_id: int, execucao_id: int, momento: datetime
) -> tuple[int, int]:
    e = EstoqueEmpresaLocalLote
    ausentes = db.execute(
        update(e)
        .where(
            e.empresa_id == empresa_id,
            e.ativo.is_(True),
            e.ultima_sincronizacao_id.is_distinct_from(execucao_id),
        )
        .values(ausencias_leitura_completa=e.ausencias_leitura_completa + 1)
        .execution_options(synchronize_session=False)
    )
    desativadas = db.execute(
        update(e)
        .where(
            e.empresa_id == empresa_id,
            e.ativo.is_(True),
            e.ausencias_leitura_completa >= AUSENCIAS_PARA_DESATIVAR,
        )
        .values(ativo=False, removido_em=momento, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    return (
        int(ausentes.rowcount or 0),  # type: ignore[attr-defined]
        int(desativadas.rowcount or 0),  # type: ignore[attr-defined]
    )


def recalcular_estoque_consolidado(
    fabrica: FabricaSessao,
    *,
    ambiente: str,
    empresas: tuple[str, ...],
    agora: Relogio = agora_utc,
) -> int:
    e = EstoqueEmpresaLocalLote
    consulta = (
        select(
            e.id_produto,
            e.id_subproduto,
            func.sum(e.saldo_atual),
            func.sum(e.saldo_reservado),
            func.sum(e.saldo_disponivel),
            func.count(distinct(e.empresa_id)).filter(e.saldo_atual > 0).cast(Integer),
            literal(agora()),
        )
        .join(Empresa, Empresa.id == e.empresa_id)
        .where(
            e.ativo.is_(True),
            Empresa.ambiente == ambiente,
            Empresa.id_erp.in_(empresas),
            fora_da_perda(),
        )
        .group_by(e.id_produto, e.id_subproduto)
    )
    with fabrica() as db, db.begin():
        db.execute(delete(EstoqueConsolidado))
        resultado = db.execute(
            insert(EstoqueConsolidado).from_select(
                [
                    "id_produto",
                    "id_subproduto",
                    "saldo_atual_total",
                    "saldo_reservado_total",
                    "saldo_disponivel_total",
                    "empresas_com_estoque",
                    "atualizado_em",
                ],
                consulta,
            )
        )
        return int(resultado.rowcount or 0)  # type: ignore[attr-defined]
