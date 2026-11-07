from datetime import date
from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api import schemas_financeiro as schemas
from app.api.autorizacao import exigir_modulo
from app.api.deps import SessionLeituraDep
from app.api.parametros import empresa_por_codigo, intervalo_de
from app.api.schemas import RESPOSTAS_PROTEGIDAS, EmpresaResumo, Erro
from app.api.schemas_vendas import CoberturaVendas
from app.dominio.intervalo import IntervaloInvalido
from app.dominio.modulos import Modulo
from app.services import financeiro as service

router = APIRouter(
    prefix="/financeiro",
    tags=["financeiro"],
    dependencies=[Depends(exigir_modulo(Modulo.FINANCEIRO))],
    responses=RESPOSTAS_PROTEGIDAS,
)


@router.get(
    "/resumo",
    summary="Vendido, pago, pendente e recebido por forma de pagamento",
    description=(
        "Parcelas (títulos) da série PDV, lidas do ERP pela sincronização de vendas.\n\n"
        "Vendas: parcelas lançadas no período, com o valor das vendas, o já pago e o "
        "pendente. Recebidos: o pago das parcelas com o último recebimento no período, de "
        "qualquer venda (boleto pago de venda antiga inclusive), e quanto disso é de vendas "
        "lançadas fora do período."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def resumo_financeiro(
    db: SessionLeituraDep,
    empresa: Annotated[
        str | None, Query(description="Código da empresa. Ausente = consolidado.", examples=["1"])
    ] = None,
    data_inicial: Annotated[date | None, Query(description="Início do período.")] = None,
    data_final: Annotated[date | None, Query(description="Fim do período, inclusive.")] = None,
) -> schemas.ResumoFinanceiro:
    try:
        periodo = intervalo_de("data_inicial", data_inicial, "data_final", data_final)
    except IntervaloInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    empresa_filtro = empresa_por_codigo(db, empresa) if empresa else None

    r = service.resumo_financeiro(db, empresa_filtro, periodo)
    v, rec = r.vendas, r.recebidos
    return schemas.ResumoFinanceiro(
        gerado_em=r.gerado_em,
        filtro=schemas.FiltroFinanceiro(
            empresa=EmpresaResumo.model_validate(empresa_filtro) if empresa_filtro else None,
            data_inicial=periodo.inicio if periodo else None,
            data_final=periodo.fim if periodo else None,
        ),
        vendas=schemas.VendasPagas(
            valor=v.valor,
            valor_pago=v.valor_pago,
            valor_pendente=v.valor_pendente,
            parcelas=v.parcelas,
            formas=[
                schemas.FormaVendida(
                    forma=f.forma,
                    valor=f.valor,
                    valor_pago=f.valor_pago,
                    valor_pendente=f.valor_pendente,
                    parcelas=f.parcelas,
                )
                for f in v.formas
            ],
        ),
        recebidos=schemas.Recebidos(
            total=rec.total,
            de_vendas_anteriores=rec.de_vendas_anteriores,
            de_boletos=rec.de_boletos,
            das_vendas_do_periodo=rec.das_vendas_do_periodo,
            outros_anteriores=rec.outros_anteriores,
            juros=rec.juros,
            titulos=rec.titulos,
            formas=[
                schemas.FormaRecebida(forma=f.forma, valor=f.valor, titulos=f.titulos)
                for f in rec.formas
            ],
        ),
        cobertura=CoberturaVendas(
            desde=r.cobertura.desde, ate=r.cobertura.ate, atualizado_em=r.cobertura.atualizado_em
        ),
    )


TAMANHO_PAGINA_MAXIMO = 200


def _situacao(p: service.Parcela) -> Literal["PAGA", "PARCIAL", "PENDENTE"]:
    if p.valor_pendente <= 0:
        return "PAGA"
    return "PARCIAL" if p.valor_pago > 0 else "PENDENTE"


@router.get(
    "/parcelas",
    summary="Parcela por parcela, para conferir com o ERP",
    description=(
        "As parcelas (títulos) da série PDV uma a uma, com o valor, o pago, o pendente e a "
        "data do último pagamento, como vieram do ERP. `data_por=lancamento` filtra o período "
        "pelo dia da venda (bate com o Vendido); `data_por=pagamento`, pelo dia do último "
        "pagamento (bate com o Recebido). Os totais são do filtro inteiro, não só da página."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def listar_parcelas(
    db: SessionLeituraDep,
    empresa: Annotated[
        str | None, Query(description="Código da empresa. Ausente = todas.", examples=["1"])
    ] = None,
    data_inicial: Annotated[date | None, Query(description="Início do período.")] = None,
    data_final: Annotated[date | None, Query(description="Fim do período, inclusive.")] = None,
    data_por: Annotated[
        service.DataParcela, Query(description="Qual data o período filtra.")
    ] = "lancamento",
    situacao: Annotated[
        service.SituacaoParcela,
        Query(description="pagas: nada pendente; pendentes: algo a pagar (parciais inclusive)."),
    ] = "todas",
    forma: Annotated[
        str | None, Query(description="Forma exata, como vem no resumo.", examples=["PIX TEF"])
    ] = None,
    pagina: Annotated[int, Query(ge=1, description="Página, começando em 1.")] = 1,
    tamanho_pagina: Annotated[
        int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Parcelas por página.")
    ] = 50,
) -> schemas.PaginaParcelas:
    try:
        periodo = intervalo_de("data_inicial", data_inicial, "data_final", data_final)
    except IntervaloInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    empresa_filtro = empresa_por_codigo(db, empresa) if empresa else None

    r = service.listar_parcelas(
        db,
        empresa_filtro,
        periodo,
        data_por=data_por,
        situacao=situacao,
        forma=forma,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
    )
    return schemas.PaginaParcelas(
        total=r.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(r.total / tamanho_pagina),
        valor=r.valor,
        valor_pago=r.valor_pago,
        valor_pendente=r.valor_pendente,
        itens=[
            schemas.Parcela(
                empresa=p.empresa_codigo,
                empresa_nome=p.empresa_nome,
                documento=p.documento,
                titulo=p.titulo,
                parcela=p.parcela,
                forma=p.forma,
                dia_lancamento=p.dia_lancamento,
                vencimento=p.vencimento,
                dia_pagamento=p.dia_pagamento,
                valor=p.valor,
                valor_pago=p.valor_pago,
                valor_pendente=p.valor_pendente,
                juros=p.juros,
                desconto=p.desconto,
                situacao=_situacao(p),
            )
            for p in r.itens
        ],
    )
