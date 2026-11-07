from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import ScalarResult
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import Empresa, PrecoProdutoEmpresa
from app.database.models import Produto as ProdutoModel
from app.erp.errors import ErpApiError
from app.erp.schemas import RespostaPaginada
from app.erp.servicos import (
    ROTA_CAD_PRODUTOS,
    ROTA_PRECOS_CUSTOS,
    Filtros,
    PrecoProduto,
    Produto,
    RegistroInvalidoError,
    ServicosErp,
    descrever,
    mapear_preco,
    mapear_produto,
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

TIPO = "precos"
TIPO_COMPLETO = "precos_completo"

MARGEM_INCREMENTAL = timedelta(minutes=10)

_LOTE_UPSERT = 1000
_MAX_ERROS_DE_REGISTRO = 5

Relogio = Callable[[], datetime]
Registro = PrecoProduto | Produto


@dataclass
class ResultadoParte:
    nome: str
    status: str
    completa: bool = False
    paginas: int = 0
    recebidos: int = 0
    criados: int = 0
    atualizados: int = 0
    ignorados: int = 0
    mensagem: str | None = None


@dataclass(frozen=True)
class _Destino:
    rota: str
    modelo: type[ProdutoModel] | type[PrecoProdutoEmpresa]
    constraint: str
    mapear: Callable[..., Registro]
    buscar: Callable[[int, Filtros], RespostaPaginada]
    linha: Callable[[Any, int, datetime], dict[str, Any]]
    atualizaveis: tuple[str, ...]
    empresa_id: int | None = None
    id_erp: str | None = None


@dataclass
class _Traducao:
    registros: dict[tuple[str, str], Registro] = field(default_factory=dict)
    invalidos: int = 0
    de_outra_empresa: int = 0
    detalhados: int = 0
    sem_detalhe: int = 0

    @property
    def ignorados(self) -> int:
        return self.invalidos + self.de_outra_empresa


def sincronizar_precos(
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

    partes: list[ResultadoParte] = []
    interrupcao: str | None = None
    try:
        com_retry(servicos.autenticar, politica, lambda exc, t: erros.erpapi(exc, tentativa=t))
        partes.append(
            _sincronizar_parte(
                fabrica,
                tipo,
                _destino_produtos(servicos),
                servicos=servicos,
                pai_id=pai_id,
                politica=politica,
                completa=completa,
                agora=agora,
            )
        )
        for id_erp in empresas:
            if id_erp not in cadastradas:
                continue
            partes.append(
                _sincronizar_parte(
                    fabrica,
                    tipo,
                    _destino_precos(servicos, cadastradas[id_erp], id_erp),
                    servicos=servicos,
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
        logger.exception("sync.precos.falha_interna execucao=%s", pai_id)
        finalizar_execucao_isolada(fabrica, pai_id, "erro", mensagem=resumir(exc))
        raise

    ok = [p for p in partes if p.status != "erro"]
    esperadas = 1 + len(cadastradas)
    mensagens: list[str] = []
    if interrupcao:
        mensagens.append(interrupcao)
    if nao_cadastradas:
        mensagens.append(f"empresas nao cadastradas: {', '.join(nao_cadastradas)}")
    mensagens += [f"{p.nome}: {p.mensagem}" for p in partes if p.mensagem]

    if interrupcao or not ok:
        status = "erro"
    elif len(ok) == esperadas and not nao_cadastradas and all(p.status == "sucesso" for p in ok):
        status = "sucesso"
    else:
        status = "parcial"

    mensagem = "; ".join(mensagens) or None
    finalizar_execucao_isolada(
        fabrica,
        pai_id,
        status,
        mensagem=mensagem,
        empresas_processadas=sum(1 for p in ok if p.nome != "produtos"),
        paginas_processadas=sum(p.paginas for p in partes),
        registros_consultados=sum(p.recebidos for p in partes),
        registros_criados=sum(p.criados for p in partes),
        registros_atualizados=sum(p.atualizados for p in partes),
        registros_ignorados=sum(p.ignorados for p in partes),
    )
    logger.info(
        "sync.precos.fim tipo=%s execucao=%s status=%s partes_ok=%s/%s",
        tipo,
        pai_id,
        status,
        len(ok),
        esperadas,
    )
    return ResultadoSincronizacao(pai_id, status, mensagem)


def _sincronizar_parte(
    fabrica: FabricaSessao,
    tipo: str,
    destino: _Destino,
    *,
    servicos: ServicosErp,
    pai_id: int,
    politica: PoliticaRetry,
    completa: bool,
    agora: Relogio,
) -> ResultadoParte:
    nome = f"empresa {destino.id_erp}" if destino.id_erp else "produtos"
    execucao_id = iniciar_execucao(fabrica, tipo, empresa_id=destino.empresa_id, pai_id=pai_id)
    erros = RegistroErros(fabrica, execucao_id)
    leitura = Leitura()

    ultima = None if completa else _ultima_alteracao(fabrica, destino)
    ultima = limitar_cursor(ultima, agora(), f"precos {nome}")
    le_tudo = ultima is None
    filtros: Filtros = (
        servicos.filtro_alterado_desde(ultima - MARGEM_INCREMENTAL) if ultima is not None else ()
    )
    pedido = ", ".join(
        p
        for p in (
            f"idempresa IGUAL {destino.id_erp}" if destino.id_erp else "",
            descrever(filtros),
        )
        if p
    )

    try:
        percorrer_paginas(
            lambda pagina: destino.buscar(pagina, filtros),
            max_paginas=servicos.max_paginas,
            politica=politica,
            ao_falhar=lambda exc, tentativa, pagina: erros.erpapi(
                exc,
                tentativa=tentativa,
                id_empresa=destino.id_erp,
                pedido=f"page={pagina}, clausulas=[{pedido}]",
            ),
            leitura=leitura,
        )
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
        return ResultadoParte(
            nome,
            "erro",
            completa=le_tudo,
            paginas=leitura.paginas,
            recebidos=len(leitura.registros),
            mensagem=mensagem,
        )

    traducao = _traduzir(leitura.registros, destino, erros, servicos)
    resultado = ResultadoParte(
        nome,
        "sucesso",
        completa=le_tudo,
        paginas=leitura.paginas,
        recebidos=len(leitura.registros),
        ignorados=traducao.ignorados,
    )
    if le_tudo and leitura.registros and not traducao.registros:
        resultado.status = "erro"
        resultado.mensagem = (
            f"nenhum registro valido em {len(leitura.registros)} recebido(s); "
            "dados anteriores mantidos"
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
    if traducao.ignorados:
        resultado.status = "parcial"
        partes = [
            f"{n} {rotulo}"
            for n, rotulo in (
                (traducao.invalidos, "invalido(s)"),
                (traducao.de_outra_empresa, "de outra empresa"),
            )
            if n
        ]
        resultado.mensagem = "registros ignorados: " + ", ".join(partes)

    try:
        with fabrica() as db, db.begin():
            resultado.criados, resultado.atualizados = _gravar(
                db, destino, execucao_id, traducao.registros.values(), agora()
            )
            finalizar_execucao(
                db,
                execucao_id,
                resultado.status,
                mensagem=resultado.mensagem,
                empresas_processadas=1 if destino.empresa_id else 0,
                paginas_processadas=resultado.paginas,
                registros_consultados=resultado.recebidos,
                registros_criados=resultado.criados,
                registros_atualizados=resultado.atualizados,
                registros_ignorados=resultado.ignorados,
            )
    except Exception as exc:
        logger.exception("sync.precos.gravacao_falhou parte=%s", nome)
        resultado.status = "erro"
        resultado.mensagem = f"falha ao gravar: {resumir(exc)}"
        resultado.criados = resultado.atualizados = 0
        finalizar_execucao_isolada(fabrica, execucao_id, "erro", mensagem=resultado.mensagem)
        return resultado

    logger.info(
        "sync.precos.parte parte=%s modo=%s status=%s paginas=%s recebidos=%s "
        "criados=%s atualizados=%s ignorados=%s",
        nome,
        "completa" if le_tudo else "incremental",
        resultado.status,
        resultado.paginas,
        resultado.recebidos,
        resultado.criados,
        resultado.atualizados,
        resultado.ignorados,
    )
    return resultado


def _ultima_alteracao(fabrica: FabricaSessao, destino: _Destino) -> datetime | None:
    m = destino.modelo
    consulta = select(func.max(m.data_alteracao_erp))
    if destino.empresa_id is not None:
        consulta = consulta.where(PrecoProdutoEmpresa.empresa_id == destino.empresa_id)
    with fabrica() as db:
        return db.scalar(consulta)


_CONTROLE = ("data_alteracao_erp", "inativo_erp", "sincronizado_em", "ultima_sincronizacao_id")

_ATUALIZAVEIS_PRODUTO = (
    "descricao",
    "descricao_resumida",
    "referencia",
    "codigo_barras",
    "embalagem_saida",
    "marca",
    "divisao",
    "secao",
    "grupo",
    "subgrupo",
    "bloqueado_venda",
    *_CONTROLE,
)

_ATUALIZAVEIS_PRECO = (
    "preco_varejo",
    "preco_promocao_varejo",
    "inicio_promocao_varejo",
    "fim_promocao_varejo",
    "preco_atacado",
    "preco_promocao_atacado",
    "inicio_promocao_atacado",
    "fim_promocao_atacado",
    "custo_reposicao",
    "custo_gerencial",
    "custo_nota_fiscal",
    *_CONTROLE,
)


def _controle(r: Registro, execucao_id: int, momento: datetime) -> dict[str, Any]:
    return {
        "id_produto": r.id_produto,
        "id_subproduto": r.id_subproduto,
        "data_alteracao_erp": r.data_alteracao,
        "inativo_erp": r.inativo_erp,
        "sincronizado_em": momento,
        "ultima_sincronizacao_id": execucao_id,
    }


def _linha_produto(p: Produto, execucao_id: int, momento: datetime) -> dict[str, Any]:
    return {
        **_controle(p, execucao_id, momento),
        **{c: getattr(p, c) for c in _ATUALIZAVEIS_PRODUTO if c not in _CONTROLE},
    }


def _destino_produtos(servicos: ServicosErp) -> _Destino:
    return _Destino(
        rota=ROTA_CAD_PRODUTOS,
        modelo=ProdutoModel,
        constraint="uq_produtos_produto",
        mapear=mapear_produto,
        buscar=servicos.pagina_produtos,
        linha=_linha_produto,
        atualizaveis=_ATUALIZAVEIS_PRODUTO,
    )


def _destino_precos(servicos: ServicosErp, empresa_id: int, id_erp: str) -> _Destino:
    def linha(p: PrecoProduto, execucao_id: int, momento: datetime) -> dict[str, Any]:
        return {
            "empresa_id": empresa_id,
            **_controle(p, execucao_id, momento),
            **{c: getattr(p, c) for c in _ATUALIZAVEIS_PRECO if c not in _CONTROLE},
        }

    return _Destino(
        rota=ROTA_PRECOS_CUSTOS,
        modelo=PrecoProdutoEmpresa,
        constraint="uq_precos_produto_empresa_chave",
        mapear=mapear_preco,
        buscar=lambda pagina, filtros: servicos.pagina_precos(id_erp, pagina, filtros),
        linha=linha,
        atualizaveis=_ATUALIZAVEIS_PRECO,
        empresa_id=empresa_id,
        id_erp=id_erp,
    )


def _traduzir(
    registros: list[dict[str, Any]],
    destino: _Destino,
    erros: RegistroErros,
    servicos: ServicosErp,
) -> _Traducao:
    traducao = _Traducao()

    def _recusar(tipo: str, mensagem: str) -> None:
        if traducao.detalhados < _MAX_ERROS_DE_REGISTRO:
            traducao.detalhados += 1
            erros.outro(tipo, mensagem, id_empresa=destino.id_erp, endpoint=destino.rota)
        else:
            traducao.sem_detalhe += 1

    for bruto in registros:
        try:
            registro = destino.mapear(bruto, servicos.fuso)
        except RegistroInvalidoError as exc:
            traducao.invalidos += 1
            _recusar("RegistroInvalido", str(exc))
            continue
        if isinstance(registro, PrecoProduto) and registro.id_empresa != destino.id_erp:
            traducao.de_outra_empresa += 1
            _recusar(
                "RegistroDeOutraEmpresa",
                f"pedido idempresa={destino.id_erp}, veio idempresa={registro.id_empresa}",
            )
            continue

        traducao.registros[registro.chave] = registro

    if traducao.sem_detalhe:
        erros.outro(
            "RegistrosIgnorados",
            f"{traducao.sem_detalhe} outro(s) registro(s) ignorado(s) sem detalhe individual",
            id_empresa=destino.id_erp,
            endpoint=destino.rota,
        )
    return traducao


def _gravar(
    db: Session,
    destino: _Destino,
    execucao_id: int,
    registros: Iterable[Registro],
    momento: datetime,
) -> tuple[int, int]:
    linhas = [destino.linha(r, execucao_id, momento) for r in registros]
    criados = 0
    for inicio in range(0, len(linhas), _LOTE_UPSERT):
        valores = insert(destino.modelo).values(linhas[inicio : inicio + _LOTE_UPSERT])
        upsert = valores.on_conflict_do_update(
            constraint=destino.constraint,
            set_={
                **{c: valores.excluded[c] for c in destino.atualizaveis},
                "updated_at": func.now(),
            },
        )
        novos: ScalarResult[bool] = db.scalars(
            upsert.returning(literal_column("(xmax = 0)").label("criado"))
        )
        criados += sum(1 for criado in novos if criado)
    return criados, len(linhas) - criados
