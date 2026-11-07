from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.erp.errors import ErpApiError
from app.erp.servicos import ServicosErp
from app.sync.comum import (
    FabricaSessao,
    FalhaGeralError,
    PoliticaRetry,
    RegistroErros,
    agora_utc,
    com_retry,
    finalizar_execucao_isolada,
    iniciar_execucao,
    resumir,
)
from app.sync.empresas import ResultadoSincronizacao
from app.sync.transferencias import Resultado, _carregar_empresas, _Empresas

logger = get_logger(__name__)

Relogio = Callable[[], datetime]


class SincronizarEmpresa(Protocol):
    def __call__(
        self,
        fabrica: FabricaSessao,
        servicos: ServicosErp,
        cadastro: _Empresas,
        *,
        id_erp: str,
        dias: list[date],
        pai_id: int | None,
        politica: PoliticaRetry,
        agora: Relogio,
    ) -> Resultado: ...


def dias_a_ler(
    db: Session,
    modelo_dia: Any,
    empresa_id: int,
    *,
    versao: int,
    hoje: date,
    janela_dias: int,
    historico_dias: int,
    dias_por_ciclo: int,
) -> list[date]:
    janela = [hoje - timedelta(days=n) for n in range(janela_dias)]
    inicio = hoje - timedelta(days=historico_dias - 1)
    antes_da_janela = hoje - timedelta(days=janela_dias)
    lidos = set(
        db.scalars(
            select(modelo_dia.dia).where(
                modelo_dia.empresa_id == empresa_id,
                modelo_dia.dia >= inicio,
                modelo_dia.dia <= antes_da_janela,
                modelo_dia.versao >= versao,
            )
        )
    )
    faltando: list[date] = []
    dia = antes_da_janela
    while dia >= inicio and len(faltando) < dias_por_ciclo:
        if dia not in lidos:
            faltando.append(dia)
        dia -= timedelta(days=1)
    return janela + faltando


def sincronizar_por_dia(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    tipo: str,
    modelo_dia: Any,
    versao: int,
    sincronizar_empresa: SincronizarEmpresa,
    ambiente: str,
    empresas: tuple[str, ...],
    politica: PoliticaRetry,
    janela_dias: int,
    historico_dias: int,
    dias_por_ciclo: int,
    agora: Relogio = agora_utc,
    depois_das_empresas: Callable[[RegistroErros], object] | None = None,
) -> ResultadoSincronizacao:
    pai_id = iniciar_execucao(fabrica, tipo)
    erros = RegistroErros(fabrica, pai_id)
    cadastro = _carregar_empresas(fabrica, ambiente)
    nao_cadastradas = [e for e in empresas if e not in cadastro.por_id_erp]
    for id_erp in nao_cadastradas:
        erros.outro(
            "EmpresaNaoCadastrada",
            f"empresa {id_erp} nao esta na tabela empresas ({ambiente}); "
            "rode a sincronizacao de empresas antes",
            id_empresa=id_erp,
        )

    hoje = agora().astimezone(servicos.fuso).date()
    resultados: list[Resultado] = []
    interrupcao: str | None = None
    try:
        com_retry(servicos.autenticar, politica, lambda exc, t: erros.erpapi(exc, tentativa=t))
        for id_erp in empresas:
            if id_erp not in cadastro.por_id_erp:
                continue
            with fabrica() as db:
                dias = dias_a_ler(
                    db,
                    modelo_dia,
                    cadastro.por_id_erp[id_erp],
                    versao=versao,
                    hoje=hoje,
                    janela_dias=janela_dias,
                    historico_dias=historico_dias,
                    dias_por_ciclo=dias_por_ciclo,
                )
            resultados.append(
                sincronizar_empresa(
                    fabrica,
                    servicos,
                    cadastro,
                    id_erp=id_erp,
                    dias=dias,
                    pai_id=pai_id,
                    politica=politica,
                    agora=agora,
                )
            )
        if depois_das_empresas is not None:
            depois_das_empresas(erros)
    except FalhaGeralError as exc:
        interrupcao = f"interrompida: {exc}"
    except ErpApiError as exc:
        interrupcao = f"interrompida: {resumir(exc)}"
    except Exception as exc:
        logger.exception("sync.%s.falha_interna execucao=%s", tipo, pai_id)
        finalizar_execucao_isolada(fabrica, pai_id, "erro", mensagem=resumir(exc))
        raise

    ok = [r for r in resultados if r.status != "erro"]
    mensagens: list[str] = []
    if interrupcao:
        mensagens.append(interrupcao)
    if nao_cadastradas:
        mensagens.append(f"empresas nao cadastradas: {', '.join(nao_cadastradas)}")
    mensagens += [f"{r.rotulo}: {r.mensagem}" for r in resultados if r.mensagem]

    esperados = len(empresas) - len(nao_cadastradas)
    if interrupcao or not ok:
        status = "erro"
    elif len(ok) == esperados and not nao_cadastradas and all(r.status == "sucesso" for r in ok):
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
    logger.info("sync.%s.fim execucao=%s status=%s", tipo, pai_id, status)
    return ResultadoSincronizacao(pai_id, status, mensagem)
