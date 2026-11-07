from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import Empresa
from app.erp.errors import ErpApiError
from app.erp.servicos import ROTA_CAD_LOJAS, Loja, RegistroInvalidoError, ServicosErp, mapear_loja
from app.sync.comum import (
    FabricaSessao,
    Leitura,
    PoliticaRetry,
    RegistroErros,
    com_retry,
    finalizar_execucao,
    finalizar_execucao_isolada,
    iniciar_execucao,
    percorrer_paginas,
    resumir,
)

logger = get_logger(__name__)

TIPO = "empresas"


_MAX_ERROS_DE_REGISTRO = 5


@dataclass
class ResultadoSincronizacao:
    sincronizacao_id: int
    status: str
    mensagem: str | None = None


def sincronizar_empresas(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    ambiente: str,
    empresas_ativas: tuple[str, ...],
    politica: PoliticaRetry,
) -> ResultadoSincronizacao:
    execucao_id = iniciar_execucao(fabrica, TIPO)
    erros = RegistroErros(fabrica, execucao_id)
    leitura = Leitura()

    def _falhou(exc: ErpApiError, tentativa: int, pagina: int = 0) -> None:
        erros.erpapi(exc, tentativa=tentativa, pedido=f"page={pagina}" if pagina else None)

    try:
        com_retry(servicos.autenticar, politica, _falhou)
        percorrer_paginas(
            servicos.pagina_lojas,
            max_paginas=servicos.max_paginas,
            politica=politica,
            ao_falhar=_falhou,
            leitura=leitura,
        )
    except ErpApiError as exc:
        falha = resumir(exc)
        finalizar_execucao_isolada(
            fabrica,
            execucao_id,
            "erro",
            mensagem=falha,
            paginas_processadas=leitura.paginas,
            registros_consultados=len(leitura.registros),
        )
        return ResultadoSincronizacao(execucao_id, "erro", falha)

    lojas: dict[str, Loja] = {}
    ignorados = 0
    for bruto in leitura.registros:
        try:
            loja = mapear_loja(bruto)
        except RegistroInvalidoError as exc:
            ignorados += 1
            if ignorados <= _MAX_ERROS_DE_REGISTRO:
                erros.outro("RegistroInvalido", str(exc), endpoint=ROTA_CAD_LOJAS)
            continue
        lojas[loja.id_erp] = loja

    try:
        with fabrica() as db, db.begin():
            criados, atualizados = _gravar(db, lojas.values(), ambiente, empresas_ativas)
            status = "parcial" if ignorados else "sucesso"
            mensagem = f"{ignorados} registro(s) invalido(s) ignorado(s)" if ignorados else None
            finalizar_execucao(
                db,
                execucao_id,
                status,
                mensagem=mensagem,
                empresas_processadas=len(lojas),
                paginas_processadas=leitura.paginas,
                registros_consultados=len(leitura.registros),
                registros_criados=criados,
                registros_atualizados=atualizados,
                registros_ignorados=ignorados,
            )
    except Exception as exc:
        logger.exception("sync.empresas.gravacao_falhou execucao=%s", execucao_id)
        finalizar_execucao_isolada(fabrica, execucao_id, "erro", mensagem=resumir(exc))
        return ResultadoSincronizacao(execucao_id, "erro", resumir(exc))

    nao_encontradas = sorted(set(empresas_ativas) - set(lojas))
    if nao_encontradas:
        logger.warning("sync.empresas.configuradas_ausentes ids=%s", ",".join(nao_encontradas))
    logger.info(
        "sync.empresas.fim execucao=%s status=%s lojas=%s criadas=%s atualizadas=%s",
        execucao_id,
        status,
        len(lojas),
        criados,
        atualizados,
    )
    return ResultadoSincronizacao(execucao_id, status, mensagem)


def _gravar(
    db: Session, lojas: Iterable[Loja], ambiente: str, empresas_ativas: tuple[str, ...]
) -> tuple[int, int]:
    existentes = {
        e.id_erp: e
        for e in db.scalars(
            select(Empresa).where(
                Empresa.ambiente == ambiente,
                Empresa.id_erp.in_([loja.id_erp for loja in lojas]),
            )
        )
    }
    criados = atualizados = 0
    for loja in lojas:
        ativo = loja.id_erp in empresas_ativas
        empresa = existentes.get(loja.id_erp)
        if empresa is None:
            db.add(
                Empresa(
                    id_erp=loja.id_erp,
                    ambiente=ambiente,
                    codigo=loja.id_erp,
                    nome=loja.nome,
                    bairro=loja.bairro,
                    cnpj=loja.cnpj,
                    ativo=ativo,
                )
            )
            criados += 1
            continue
        novos = {"nome": loja.nome, "bairro": loja.bairro, "cnpj": loja.cnpj, "ativo": ativo}
        if any(getattr(empresa, campo) != valor for campo, valor in novos.items()):
            for campo, valor in novos.items():
                setattr(empresa, campo, valor)
            atualizados += 1
    db.flush()
    return criados, atualizados
