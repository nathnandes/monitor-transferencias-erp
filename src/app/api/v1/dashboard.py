from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api import schemas
from app.api.autorizacao import exigir_modulo
from app.api.deps import SessionLeituraDep, SettingsDep
from app.api.parametros import empresa_por_codigo, intervalo_de
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.dominio.intervalo import IntervaloInvalido
from app.dominio.modulos import Modulo
from app.services import dashboard as service
from app.services import indicadores

router = APIRouter(
    tags=["dashboard"],
    dependencies=[Depends(exigir_modulo(Modulo.DASHBOARD))],
    responses=RESPOSTAS_PROTEGIDAS,
)


@router.get(
    "/dashboard/resumo",
    summary="Indicadores consolidados para o painel operacional",
    description=(
        "Derivado somente do banco próprio. Regra de `status_por_empresa`: "
        "`critico` se a última sincronização da empresa terminou em `erro`, se há "
        "transferência de origem nela com status ERRO ou PENDENTE há mais que o limite de "
        "crítico; `atencao` se a última sincronização foi `parcial`, se não há sincronização "
        "registrada ou se há PENDENTE há mais que o limite de atenção; `ok` caso contrário. "
        "Os limites (padrão 24h e 48h) vêm em `limites_pendencia`.\n\n"
        "Filtros opcionais: `empresa` (transferências em que ela é origem **ou** destino), "
        "`data_inicial`/`data_final` (dias no fuso `TZ`, inclusivos) e o intervalo de "
        "comparação `comparar_inicial`/`comparar_final`, que exige período. O período não "
        "recorta `situacao_atual` nem `status_por_empresa`."
    ),
    responses={404: {"model": schemas.Erro, "description": "Empresa não encontrada."}},
)
def resumo_dashboard(
    db: SessionLeituraDep,
    settings: SettingsDep,
    empresa: Annotated[
        str | None, Query(description="Código da empresa. Ausente = consolidado.", examples=["01"])
    ] = None,
    data_inicial: Annotated[date | None, Query(description="Início do período.")] = None,
    data_final: Annotated[date | None, Query(description="Fim do período, inclusive.")] = None,
    comparar_inicial: Annotated[
        date | None, Query(description="Início do intervalo de comparação.")
    ] = None,
    comparar_final: Annotated[
        date | None, Query(description="Fim do intervalo de comparação, inclusive.")
    ] = None,
) -> schemas.ResumoDashboard:
    try:
        periodo = intervalo_de("data_inicial", data_inicial, "data_final", data_final)
        comparacao = intervalo_de(
            "comparar_inicial", comparar_inicial, "comparar_final", comparar_final
        )
        filtro = service.FiltroResumo(
            empresa=empresa_por_codigo(db, empresa) if empresa else None,
            periodo=periodo,
            comparacao=comparacao,
        )
    except IntervaloInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    resumo = service.resumo_dashboard(db, filtro=filtro, tz=ZoneInfo(settings.tz))
    return schemas.ResumoDashboard(
        gerado_em=resumo.gerado_em,
        filtro=schemas.FiltroResumo(
            empresa=(
                schemas.EmpresaResumo.model_validate(filtro.empresa) if filtro.empresa else None
            ),
            data_inicial=periodo.inicio if periodo else None,
            data_final=periodo.fim if periodo else None,
            comparar_inicial=comparacao.inicio if comparacao else None,
            comparar_final=comparacao.fim if comparacao else None,
        ),
        periodo=_fluxo(resumo.periodo),
        comparacao=_fluxo(resumo.comparacao),
        situacao_atual=schemas.SituacaoAtual(
            pendentes=resumo.situacao_atual.pendentes,
            pendentes_atrasadas=resumo.situacao_atual.pendentes_atrasadas,
            com_erro=resumo.situacao_atual.com_erro,
        ),
        transferencias=schemas.TotaisTransferencias(
            total=resumo.total,
            processadas=resumo.processadas,
            pendentes=resumo.pendentes,
            com_erro=resumo.com_erro,
        ),
        empresas_ativas=resumo.empresas_ativas,
        ultima_sincronizacao=(
            schemas.SincronizacaoComEmpresa.model_validate(resumo.ultima_sincronizacao)
            if resumo.ultima_sincronizacao
            else None
        ),
        eventos_por_severidade=resumo.eventos_por_severidade,
        status_por_empresa=[
            schemas.StatusEmpresa(
                empresa=schemas.EmpresaResumo.model_validate(s.empresa),
                status=s.status,
                motivos=s.motivos,
                ultima_sincronizacao=(
                    schemas.Sincronizacao.model_validate(s.ultima_sincronizacao)
                    if s.ultima_sincronizacao
                    else None
                ),
                pendentes=s.contagem.pendentes,
                pendentes_atrasadas=s.contagem.pendentes_atrasadas,
                pendentes_criticas=s.contagem.pendentes_criticas,
                com_erro=s.contagem.com_erro,
            )
            for s in resumo.status_por_empresa
        ],
        limites_pendencia=schemas.LimitesHoras(
            horas_atencao=resumo.limites.horas_atencao,
            horas_critico=resumo.limites.horas_critico,
        ),
    )


@router.get(
    "/dashboard/indicadores-empresas",
    summary="Indicadores por empresa, em série temporal",
    description=(
        "Para cada empresa ativa, como destino: a receber, recebidas, taxa e tempo médio "
        "de entrada; como origem: enviadas, itens enviados e aguardando o destino; e COI "
        "errado dos dois lados. Em baldes "
        "de hora (período de 1 dia), dia (até 62 dias) ou mês. Sem período: da primeira "
        "transferência até hoje (no máximo 24 meses). Regras detalhadas em "
        "`app.services.indicadores`."
    ),
    responses={404: {"model": schemas.Erro, "description": "Empresa não encontrada."}},
)
def indicadores_empresas(
    db: SessionLeituraDep,
    settings: SettingsDep,
    empresa: Annotated[
        str | None, Query(description="Código da empresa. Ausente = todas.", examples=["01"])
    ] = None,
    data_inicial: Annotated[date | None, Query(description="Início do período.")] = None,
    data_final: Annotated[date | None, Query(description="Fim do período, inclusive.")] = None,
) -> schemas.IndicadoresPorEmpresa:
    try:
        periodo = intervalo_de("data_inicial", data_inicial, "data_final", data_final)
    except IntervaloInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    resultado = indicadores.indicadores_por_empresa(
        db,
        periodo=periodo,
        empresa=empresa_por_codigo(db, empresa) if empresa else None,
        tz=ZoneInfo(settings.tz),
    )
    return schemas.IndicadoresPorEmpresa(
        gerado_em=resultado.gerado_em,
        granularidade=resultado.granularidade,
        data_inicial=resultado.inicio,
        data_final=resultado.fim,
        empresas=[
            schemas.IndicadoresEmpresa(
                empresa=schemas.EmpresaResumo.model_validate(e.empresa),
                totais=_ponto(e.totais),
                serie=[_ponto(p) for p in e.serie],
            )
            for e in resultado.empresas
        ],
    )


def _ponto(p: indicadores.Ponto) -> schemas.PontoIndicadores:
    return schemas.PontoIndicadores(
        chave=p.chave,
        a_receber=p.a_receber,
        recebidas=p.recebidas,
        taxa_entrada=p.taxa_entrada,
        tempo_medio_entrada_horas=p.tempo_medio_entrada_horas,
        enviadas=p.enviadas,
        itens_enviados=p.itens_enviados,
        aguardando_destino=p.aguardando_destino,
        coi_errado=p.coi_errado,
    )


def _fluxo(fluxo: service.Fluxo | None) -> schemas.Fluxo | None:
    if fluxo is None:
        return None
    return schemas.Fluxo(
        criadas=fluxo.criadas, processadas=fluxo.processadas, eventos=fluxo.eventos
    )
