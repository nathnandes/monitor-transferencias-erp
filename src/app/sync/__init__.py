from collections.abc import Callable
from datetime import timedelta
from typing import Literal

from app.core.config import Settings, get_settings
from app.erp.config import ErpApiSettings, get_erpapi_settings
from app.erp.servicos import ServicosErp, criar_servicos
from app.sync.comum import FabricaSessao, PoliticaRetry, trava_sincronizacao
from app.sync.empresas import ResultadoSincronizacao, sincronizar_empresas
from app.sync.estoque import recalcular_estoque_consolidado, sincronizar_estoque
from app.sync.movimentos import sincronizar_movimentos
from app.sync.precos import sincronizar_precos
from app.sync.transferencias import sincronizar_transferencias
from app.sync.vendas import sincronizar_vendas

TipoSincronizacao = Literal[
    "empresas",
    "estoque",
    "estoque_completo",
    "transferencias",
    "precos",
    "precos_completo",
    "vendas",
    "movimentos_estoque",
]

__all__ = [
    "ResultadoSincronizacao",
    "TipoSincronizacao",
    "executar",
    "erpapi_habilitado",
    "politica_retry",
    "recalcular_estoque_consolidado",
    "sincronizar_empresas",
    "sincronizar_estoque",
    "sincronizar_movimentos",
    "sincronizar_precos",
    "sincronizar_transferencias",
    "sincronizar_vendas",
    "trava_sincronizacao",
]


def erpapi_habilitado(settings: ErpApiSettings | None = None) -> bool:
    return (settings or get_erpapi_settings()).enabled


def politica_retry(settings: Settings | None = None) -> PoliticaRetry:
    settings = settings or get_settings()
    return PoliticaRetry(
        tentativas=settings.sync_retry_tentativas,
        espera_segundos=settings.sync_retry_espera_segundos,
    )


def executar(
    tipo: TipoSincronizacao,
    fabrica: FabricaSessao,
    *,
    settings: Settings | None = None,
    erpapi: ErpApiSettings | None = None,
    servicos: Callable[[], ServicosErp] | None = None,
    politica: PoliticaRetry | None = None,
) -> ResultadoSincronizacao:
    settings = settings or get_settings()
    erpapi = erpapi or get_erpapi_settings()
    politica = politica or politica_retry(settings)
    cliente = servicos() if servicos else criar_servicos(erpapi)
    try:
        if tipo == "empresas":
            return sincronizar_empresas(
                fabrica,
                cliente,
                ambiente=erpapi.ambiente,
                empresas_ativas=settings.empresas_sincronizadas,
                politica=politica,
            )
        if tipo == "transferencias":
            return sincronizar_transferencias(
                fabrica,
                cliente,
                ambiente=erpapi.ambiente,
                empresas=settings.empresas_sincronizadas,
                politica=politica,
                janela=timedelta(days=settings.sync_transferencias_janela_dias),
            )
        if tipo == "vendas":
            return sincronizar_vendas(
                fabrica,
                cliente,
                ambiente=erpapi.ambiente,
                empresas=settings.empresas_sincronizadas,
                politica=politica,
                janela_dias=settings.sync_vendas_janela_dias,
                historico_dias=settings.sync_vendas_historico_dias,
                dias_por_ciclo=settings.sync_vendas_dias_por_ciclo,
            )
        if tipo == "movimentos_estoque":
            return sincronizar_movimentos(
                fabrica,
                cliente,
                ambiente=erpapi.ambiente,
                empresas=settings.empresas_sincronizadas,
                politica=politica,
                janela_dias=settings.sync_movimentos_janela_dias,
                historico_dias=settings.sync_movimentos_historico_dias,
                dias_por_ciclo=settings.sync_movimentos_dias_por_ciclo,
            )
        if tipo in ("precos", "precos_completo"):
            return sincronizar_precos(
                fabrica,
                cliente,
                ambiente=erpapi.ambiente,
                empresas=settings.empresas_sincronizadas,
                politica=politica,
                completa=tipo == "precos_completo",
            )
        return sincronizar_estoque(
            fabrica,
            cliente,
            ambiente=erpapi.ambiente,
            empresas=settings.empresas_sincronizadas,
            politica=politica,
            completa=tipo == "estoque_completo",
        )
    finally:
        cliente.close()
