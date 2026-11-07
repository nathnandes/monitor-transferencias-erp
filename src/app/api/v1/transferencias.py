from datetime import date
from math import ceil
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import Response

from app.api import schemas
from app.api.autorizacao import exigir_modulo
from app.api.deps import SessionLeituraDep, SettingsDep
from app.api.exportacao import LIMITE_EXPORTACAO, resposta_csv
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.dominio.modulos import Modulo
from app.services import controle_transferencias, pipeline
from app.services import transferencias as service
from app.services.pipeline import SituacaoCoi

router = APIRouter(
    tags=["transferencias"],
    dependencies=[Depends(exigir_modulo(Modulo.TRANSFERENCIAS))],
    responses=RESPOSTAS_PROTEGIDAS,
)

TAMANHO_PAGINA_MAXIMO = 100


def filtros_transferencia(
    empresa_origem: Annotated[
        str | None, Query(description="Código da empresa de origem.", examples=["01"])
    ] = None,
    empresa_destino: Annotated[
        str | None, Query(description="Código da empresa de destino.", examples=["02"])
    ] = None,
    empresa: Annotated[
        str | None,
        Query(description="Código de uma empresa que seja origem OU destino.", examples=["03"]),
    ] = None,
    status_: Annotated[
        str | None,
        Query(
            alias="status",
            description="Status exato, sem diferenciar maiúsculas.",
            examples=["PENDENTE"],
        ),
    ] = None,
    situacao_coi: Annotated[
        SituacaoCoi | None,
        Query(
            description=(
                "CORRETO, ERRADO (COI de saída ou de entrada errado) "
                "ou AGUARDANDO (entrada ainda não veio)."
            )
        ),
    ] = None,
    emitida_por: Annotated[
        str | None,
        Query(
            description="Usuário do ERP que emitiu a nota de saída, sem diferenciar maiúsculas.",
            examples=["BEATRIZ"],
        ),
    ] = None,
    ocorrencia: Annotated[
        controle_transferencias.Ocorrencia | None,
        Query(
            description=(
                "Mesma regra dos cartões do painel de controle, no mesmo período e empresa: "
                "FORA_DO_PRAZO, DIVERGENTE, FISCAL ou SEM_TRATATIVA."
            )
        ),
    ] = None,
    data_inicial: Annotated[
        date | None, Query(description="Criadas a partir deste dia (YYYY-MM-DD).")
    ] = None,
    data_final: Annotated[
        date | None, Query(description="Criadas até este dia, inclusive (YYYY-MM-DD).")
    ] = None,
) -> service.FiltrosTransferencia:
    try:
        return service.FiltrosTransferencia(
            empresa_origem=empresa_origem,
            empresa_destino=empresa_destino,
            empresa=empresa,
            status=status_,
            situacao_coi=situacao_coi,
            emitida_por=emitida_por,
            ocorrencia=ocorrencia,
            data_inicial=data_inicial,
            data_final=data_final,
        )
    except service.IntervaloDeDatasInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


FiltrosDep = Annotated[service.FiltrosTransferencia, Depends(filtros_transferencia)]


@router.get(
    "/transferencias",
    summary="Lista transferências com filtros e paginação",
    description=(
        "Ordenação: `data_criacao` mais recente primeiro (nulas por último), depois `id`. "
        "Datas são dias no fuso da aplicação (`TZ`), inclusivos nos dois extremos. "
        "Não traz itens nem payload: use o detalhe."
    ),
)
def listar_transferencias(
    db: SessionLeituraDep,
    settings: SettingsDep,
    filtros: FiltrosDep,
    pagina: Annotated[int, Query(ge=1, description="Página, começando em 1.")] = 1,
    tamanho_pagina: Annotated[
        int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Itens por página.")
    ] = 20,
) -> schemas.PaginaTransferencias:
    resultado = service.listar_transferencias(
        db, filtros, pagina=pagina, tamanho_pagina=tamanho_pagina, tz=ZoneInfo(settings.tz)
    )
    return schemas.PaginaTransferencias(
        total=resultado.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(resultado.total / tamanho_pagina),
        itens=[schemas.Transferencia.model_validate(t) for t in resultado.itens],
    )


@router.get(
    "/transferencias/exportar",
    summary="Exporta as transferências filtradas em CSV (Excel)",
    description=(
        "Mesmos filtros e ordem da lista, sem paginação, até "
        f"{LIMITE_EXPORTACAO} linhas. `X-Total-Registros` traz o total encontrado."
    ),
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Arquivo CSV."}},
)
def exportar_transferencias(
    db: SessionLeituraDep, settings: SettingsDep, filtros: FiltrosDep
) -> Response:
    tz = ZoneInfo(settings.tz)
    resultado = service.listar_transferencias(
        db, filtros, pagina=1, tamanho_pagina=LIMITE_EXPORTACAO, tz=tz
    )
    linhas = (
        (
            t.numero_nota,
            t.empresa_origem.codigo,
            t.empresa_origem.nome,
            t.empresa_destino.codigo if t.empresa_destino else None,
            t.empresa_destino.nome if t.empresa_destino else None,
            t.status,
            pipeline.situacao_coi(t.status, t.problemas_coi, t.coi_entrada),
            t.coi,
            t.coi_entrada,
            t.data_criacao,
            t.data_processamento,
            t.quantidade_itens,
            t.valor_total,
            t.usuario_emissao,
            " | ".join(t.problemas_coi),
            t.chave_nfe,
        )
        for t in resultado.itens
    )
    return resposta_csv(
        "transferencias",
        (
            "Nota",
            "Origem",
            "Origem (nome)",
            "Destino",
            "Destino (nome)",
            "Status",
            "Situação COI",
            "COI saída",
            "COI entrada",
            "Emissão",
            "Entrada",
            "Itens",
            "Valor",
            "Emitida por",
            "Problemas de COI",
            "Chave NF-e",
        ),
        linhas,
        tz=tz,
        total=resultado.total,
    )


@router.get(
    "/transferencias/{id}",
    summary="Detalha uma transferência, com origem, destino e itens",
    responses={404: {"model": schemas.Erro, "description": "Transferência não encontrada."}},
)
def detalhar_transferencia(
    db: SessionLeituraDep,
    id: Annotated[int, Path(description="Id interno (campo `id` da listagem).")],
) -> schemas.TransferenciaDetalhe:
    transferencia = service.obter_transferencia(db, id)
    if transferencia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Transferência {id} não encontrada.")

    detalhe = schemas.TransferenciaDetalhe.model_validate(transferencia)
    detalhe.itens.sort(key=lambda item: item.id)
    return detalhe
