from datetime import date
from typing import Annotated, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api import schemas_vendas as schemas
from app.api.autorizacao import exigir_modulo
from app.api.deps import SessionLeituraDep, SettingsDep
from app.api.exportacao import LIMITE_EXPORTACAO, TIPO_XLSX, resposta_xlsx
from app.api.parametros import empresa_por_codigo, intervalo_de
from app.api.schemas import RESPOSTAS_PROTEGIDAS, EmpresaResumo, Erro
from app.dominio.intervalo import IntervaloInvalido
from app.dominio.modulos import Modulo
from app.services import vendas as service
from app.services.planilha_vendas import planilha_descontos, planilha_formas_pagamento

router = APIRouter(
    prefix="/vendas",
    tags=["vendas"],
    dependencies=[Depends(exigir_modulo(Modulo.VENDAS))],
    responses=RESPOSTAS_PROTEGIDAS,
)


def _datas(texto: str) -> list[date]:
    try:
        return [date.fromisoformat(parte.strip()) for parte in texto.split(",") if parte.strip()]
    except ValueError as exc:
        raise IntervaloInvalido("`dias`: use datas AAAA-MM-DD separadas por vírgula.") from exc


def _totais(t: service.Totais) -> schemas.TotaisVendas:
    return schemas.TotaisVendas(
        faturamento=t.faturamento,
        notas=t.notas,
        ticket_medio=t.ticket_medio,
        quantidade=t.quantidade,
        desconto=t.desconto,
        devolucoes=t.devolucoes,
        faturamento_liquido=t.liquido,
    )


def _vendedores(r: service.RankingVendedores) -> schemas.RankingVendedores:
    media = r.media
    return schemas.RankingVendedores(
        media_faturamento=media,
        vendedores=[
            schemas.VendasPorVendedor(
                id_vendedor=v.id_vendedor,
                nome=v.nome,
                empresas=[EmpresaResumo.model_validate(e) for e in v.empresas],
                faturamento=v.faturamento,
                notas=v.notas,
                ticket_medio=v.ticket_medio,
                faturamento_comparacao=v.faturamento_comparacao,
                abaixo_da_media=media is not None and v.faturamento < media,
            )
            for v in r.vendedores
        ],
        sem_vendedor_faturamento=r.sem_vendedor_faturamento,
        sem_vendedor_notas=r.sem_vendedor_notas,
    )


def _filtro(
    db: Session,
    empresa: str | None,
    canal: schemas.Canal | None,
    data_inicial: date | None,
    data_final: date | None,
    comparar_inicial: date | None,
    comparar_final: date | None,
    dias: str | None,
) -> service.FiltroVendas:
    try:
        periodo = intervalo_de("data_inicial", data_inicial, "data_final", data_final)
        comparacao = intervalo_de(
            "comparar_inicial", comparar_inicial, "comparar_final", comparar_final
        )
        empresa_filtro = empresa_por_codigo(db, empresa) if empresa else None
        if dias is not None:
            if periodo is not None or comparacao is not None:
                raise IntervaloInvalido("`dias` não aceita período nem comparação.")
            return service.FiltroVendas.por_dias(_datas(dias), empresa_filtro, canal)
        return service.FiltroVendas(
            empresa=empresa_filtro, periodo=periodo, comparacao=comparacao, canal=canal
        )
    except IntervaloInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get(
    "/resumo",
    summary=(
        "Faturamento, devoluções, canais, formas de pagamento, categorias, lojas, produtos "
        "e vendedores"
    ),
    description=(
        "Notas fiscais de venda não canceladas: balcão (NFC-e, COI 8300), televendas "
        "(COI 8001) e faturamento logística (COI 3001). Pedidos gerenciais (COI 3000) "
        "ficam de fora: viram nota fiscal depois e seriam contados em dobro.\n\n"
        "Filtros opcionais: `empresa`, `canal`, `data_inicial`/`data_final` (dias no fuso "
        "do ERP, inclusivos) e o intervalo de comparação `comparar_inicial`/`comparar_final`, "
        "que exige período. Sem período: todo o histórico gravado, série por mês.\n\n"
        "`dias` (datas AAAA-MM-DD separadas por vírgula, ex.: os últimos 4 sábados) no "
        "lugar do período: só esses dias contam, com um ponto por dia na série. Não "
        "aceita `data_inicial`/`data_final` nem comparação.\n\n"
        "Devoluções (notas de entrada, COI 30 e 31) e formas de pagamento (recebimentos do "
        "caixa) não têm canal: com `canal`, saem nulas.\n\n"
        "Vendedores: IDVENDEDOR das notas, com a média por vendedor e quem está abaixo dela."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def resumo_vendas(
    db: SessionLeituraDep,
    empresa: Annotated[
        str | None, Query(description="Código da empresa. Ausente = consolidado.", examples=["1"])
    ] = None,
    canal: Annotated[
        schemas.Canal | None, Query(description="balcao, televendas ou faturamento.")
    ] = None,
    data_inicial: Annotated[date | None, Query(description="Início do período.")] = None,
    data_final: Annotated[date | None, Query(description="Fim do período, inclusive.")] = None,
    comparar_inicial: Annotated[
        date | None, Query(description="Início do intervalo de comparação.")
    ] = None,
    comparar_final: Annotated[
        date | None, Query(description="Fim do intervalo de comparação, inclusive.")
    ] = None,
    dias: Annotated[
        str | None,
        Query(
            description="Dias avulsos AAAA-MM-DD separados por vírgula, no lugar do período.",
            examples=["2026-10-17,2026-10-24"],
        ),
    ] = None,
) -> schemas.ResumoVendas:
    filtro = _filtro(
        db, empresa, canal, data_inicial, data_final, comparar_inicial, comparar_final, dias
    )
    periodo, comparacao = filtro.periodo, filtro.comparacao
    r = service.resumo_vendas(db, filtro)
    return schemas.ResumoVendas(
        gerado_em=r.gerado_em,
        filtro=schemas.FiltroVendas(
            empresa=EmpresaResumo.model_validate(filtro.empresa) if filtro.empresa else None,
            data_inicial=periodo.inicio if periodo else None,
            data_final=periodo.fim if periodo else None,
            comparar_inicial=comparacao.inicio if comparacao else None,
            comparar_final=comparacao.fim if comparacao else None,
            canal=canal,
            dias=list(filtro.dias) if filtro.dias is not None else None,
        ),
        totais=_totais(r.totais),
        comparacao=_totais(r.comparacao) if r.comparacao else None,
        granularidade=r.granularidade,
        serie=[
            schemas.PontoVendas(
                chave=p.chave,
                faturamento=p.faturamento,
                notas=p.notas,
                quantidade=p.quantidade,
                devolucoes=p.devolucoes,
            )
            for p in r.serie
        ],
        por_canal=[
            schemas.VendasPorCanal(
                canal=cast(schemas.Canal, f.chave),
                rotulo=service.ROTULO_CANAL.get(f.chave, f.chave),
                faturamento=f.faturamento,
                notas=f.notas,
                quantidade=f.quantidade,
            )
            for f in r.por_canal
        ],
        por_categoria=[
            schemas.VendasPorCategoria(
                categoria=f.chave, faturamento=f.faturamento, notas=f.notas, quantidade=f.quantidade
            )
            for f in r.por_categoria
        ],
        por_empresa=[
            schemas.VendasPorEmpresa(
                empresa=EmpresaResumo.model_validate(e.empresa),
                faturamento=e.faturamento,
                notas=e.notas,
                ticket_medio=e.ticket_medio,
            )
            for e in r.por_empresa
        ],
        produtos=[
            schemas.ProdutoVendido(
                id_produto=p.id_produto,
                id_subproduto=p.id_subproduto,
                descricao=p.descricao,
                quantidade=p.quantidade,
                faturamento=p.faturamento,
            )
            for p in r.produtos
        ],
        formas_pagamento=(
            [
                schemas.FormaPagamento(forma=f.forma, valor=f.valor, parcelas=f.parcelas)
                for f in r.formas_pagamento
            ]
            if r.formas_pagamento is not None
            else None
        ),
        cobertura=schemas.CoberturaVendas(
            desde=r.cobertura.desde, ate=r.cobertura.ate, atualizado_em=r.cobertura.atualizado_em
        ),
        vendedores=_vendedores(r.vendedores),
    )


def _descricao_filtro(filtro: service.FiltroVendas, complemento: str) -> list[str]:
    empresa = (
        f"Empresa: {filtro.empresa.codigo} - {filtro.empresa.nome}"
        if filtro.empresa
        else "Empresa: todas (consolidado)"
    )
    if filtro.dias is not None:
        periodo = "Dias: " + ", ".join(f"{d:%d/%m/%Y}" for d in filtro.dias)
    elif filtro.periodo is not None:
        periodo = f"Período: {filtro.periodo.inicio:%d/%m/%Y} a {filtro.periodo.fim:%d/%m/%Y}"
    else:
        periodo = "Período: todo o histórico gravado"
    return [periodo, empresa, complemento]


@router.get(
    "/formas-pagamento/exportar",
    summary="Exporta as formas de pagamento em Excel (.xlsx), com gráfico",
    description=(
        "Os mesmos filtros de `/vendas/resumo` (a comparação é ignorada). Planilha com "
        "forma, valor recebido, quantidade de parcelas, participação, total e um gráfico "
        "de pizza nativo do Excel. Com `canal`, 422: os recebimentos não têm canal."
    ),
    response_class=Response,
    responses={
        200: {"content": {TIPO_XLSX: {}}, "description": "Planilha .xlsx."},
        404: {"model": Erro, "description": "Empresa não encontrada."},
    },
)
def exportar_formas_pagamento(
    db: SessionLeituraDep,
    settings: SettingsDep,
    empresa: Annotated[str | None, Query(description="Código da empresa.")] = None,
    canal: Annotated[schemas.Canal | None, Query(description="Não se aplica: 422.")] = None,
    data_inicial: Annotated[date | None, Query(description="Início do período.")] = None,
    data_final: Annotated[date | None, Query(description="Fim do período, inclusive.")] = None,
    comparar_inicial: Annotated[date | None, Query(description="Ignorado.")] = None,
    comparar_final: Annotated[date | None, Query(description="Ignorado.")] = None,
    dias: Annotated[str | None, Query(description="Dias avulsos AAAA-MM-DD.")] = None,
) -> Response:
    if canal is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Os recebimentos não têm canal: exporte com o filtro de canal em Todos.",
        )
    filtro = _filtro(
        db, empresa, None, data_inicial, data_final, comparar_inicial, comparar_final, dias
    )
    formas = service.formas_pagamento(db, filtro) or []
    descricao = _descricao_filtro(
        filtro, "Recebimentos do caixa (série PDV) por forma de pagamento."
    )
    conteudo = planilha_formas_pagamento(formas, descricao)
    return resposta_xlsx("vendas_formas_pagamento", conteudo, tz=ZoneInfo(settings.tz))


@router.get(
    "/descontos/exportar",
    summary="Exporta em Excel (.xlsx) os descontos das notas, por vendedor",
    description=(
        "Notas de venda não canceladas com desconto no período (obrigatório): data, hora, "
        "vendedor, desconto, loja, nota, canal e valor da nota, mais o total por vendedor. "
        "Aceita `empresa` e `canal`. O desconto vem como está no ERP: desconto igual ou maior "
        f"que o valor da nota sai em amarelo. Acima de {LIMITE_EXPORTACAO} notas, 422."
    ),
    response_class=Response,
    responses={
        200: {"content": {TIPO_XLSX: {}}, "description": "Planilha .xlsx."},
        404: {"model": Erro, "description": "Empresa não encontrada."},
    },
)
def exportar_descontos(
    db: SessionLeituraDep,
    settings: SettingsDep,
    data_inicial: Annotated[date, Query(description="Início do período.")],
    data_final: Annotated[date, Query(description="Fim do período, inclusive.")],
    empresa: Annotated[str | None, Query(description="Código da empresa.")] = None,
    canal: Annotated[schemas.Canal | None, Query(description="Canal de venda.")] = None,
) -> Response:
    filtro = _filtro(db, empresa, canal, data_inicial, data_final, None, None, None)
    notas = service.descontos_por_nota(db, filtro)
    if len(notas) > LIMITE_EXPORTACAO:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"O período tem {len(notas)} notas com desconto; o limite é {LIMITE_EXPORTACAO}. "
            "Escolha um período menor.",
        )
    complemento = f"Canal: {service.ROTULO_CANAL[canal]}." if canal else "Canal: todos."
    tz = ZoneInfo(settings.tz)
    conteudo = planilha_descontos(notas, _descricao_filtro(filtro, complemento), tz)
    return resposta_xlsx("vendas_descontos", conteudo, tz=tz)
