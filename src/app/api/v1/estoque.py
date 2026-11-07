from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from typing import Annotated, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import Response

from app.api import schemas_estoque as schemas
from app.api.autenticacao import UsuarioAutenticadoDep
from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep, SessionLeituraDep, SettingsDep
from app.api.exportacao import LIMITE_EXPORTACAO, resposta_csv
from app.api.parametros import empresa_por_codigo, intervalo_de
from app.api.schemas import RESPOSTAS_PROTEGIDAS, EmpresaResumo, Erro
from app.database.models import JustificativaAvulsa
from app.dominio.intervalo import Intervalo, IntervaloInvalido
from app.dominio.modulos import Modulo
from app.services import atividades
from app.services import balancos_estoque as balancos
from app.services import estoque as service
from app.services import excecoes_cobertura as excecoes
from app.services import justificativas_avulsas as justificativas
from app.services import livro_estoque as livro
from app.services import movimentos_estoque as movimentos
from app.services import pedido_abastecimento as pedidos

router = APIRouter(
    prefix="/estoque",
    tags=["estoque"],
    dependencies=[Depends(exigir_modulo(Modulo.ESTOQUE))],
    responses=RESPOSTAS_PROTEGIDAS,
)

TAMANHO_PAGINA_MAXIMO = 100


MediaDep = Annotated[
    service.FonteMedia,
    Query(
        description="Base da venda média: vendas (as notas) ou baixa (o que a venda tirou do "
        "estoque no livro, menos as devoluções; é a da aba Loja)."
    ),
]


def _exigir_empresa(local: str | None, empresa: str | None) -> None:
    if local is not None and not empresa:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "`local` exige `empresa`.")


def filtros_estoque(
    produto: Annotated[
        str | None, Query(description="Código exato do produto.", examples=["9798"])
    ] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
    local: Annotated[
        str | None,
        Query(
            description="Local de estoque (id_local_estoque); exige `empresa`. Inclui os "
            "locais somados a ele (ESTOQUE_LOCAIS_SOMADOS).",
            examples=["1"],
        ),
    ] = None,
    situacao: Annotated[
        service.Situacao | None,
        Query(description="com_saldo (> 0), sem_saldo (= 0), negativo (< 0) ou com_reserva."),
    ] = None,
    ordenacao: Annotated[
        service.Ordenacao,
        Query(
            description="produto, maior_saldo, menor_saldo, menor_cobertura (rupturas de quem "
            "mais vende primeiro) ou maior_cobertura."
        ),
    ] = "produto",
    cobertura: Annotated[
        service.StatusCobertura | None,
        Query(description="Classificação de cobertura: " + schemas.DESCRICAO_STATUS_COBERTURA),
    ] = None,
    media: MediaDep = "vendas",
    fornecedor: Annotated[
        str | None,
        Query(
            description="CNPJ do fornecedor, só dígitos (GET /estoque/fornecedores): itens "
            "com alguma compra dele no histórico, não só na última."
        ),
    ] = None,
    so_locais_da_loja: Annotated[
        bool,
        Query(
            description="Com `empresa`: sem os locais que não são de venda "
            "(ESTOQUE_LOCAIS_FORA_DA_LOJA: trocas, avarias...) e sem a falta que nenhum "
            "depósito de abastecimento pode mandar, como na aba Loja."
        ),
    ] = False,
) -> service.FiltrosEstoque:
    _exigir_empresa(local, empresa)
    return service.FiltrosEstoque(
        produto=produto,
        empresa=empresa,
        local=local,
        situacao=situacao,
        ordenacao=ordenacao,
        cobertura=cobertura,
        media=media,
        fornecedor=fornecedor,
        so_locais_da_loja=so_locais_da_loja,
    )


FiltrosDep = Annotated[service.FiltrosEstoque, Depends(filtros_estoque)]


def janela_vendas(
    settings: SettingsDep,
    janela_dias: Annotated[
        int,
        Query(
            ge=7,
            le=180,
            description="Dias de venda (completos, até ontem) usados na média diária.",
        ),
    ] = service.JANELA_VENDAS_PADRAO,
) -> service.JanelaVendas:
    hoje = datetime.now(ZoneInfo(settings.tz)).date()
    return service.JanelaVendas.ultimos(janela_dias, hoje)


JanelaDep = Annotated[service.JanelaVendas, Depends(janela_vendas)]


def _janela(janela: service.JanelaVendas) -> schemas.JanelaVendas:
    return schemas.JanelaVendas(inicio=janela.inicio, fim=janela.fim, dias=janela.dias)


@router.get(
    "",
    summary="Lista o estoque por produto, com filtros e paginação",
    description=(
        "Sem `empresa`: estoque consolidado (soma das empresas). Com `empresa`: só o estoque "
        "daquela empresa (soma dos locais). Ordem padrão: código do produto, numérico."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def listar_estoque(
    db: SessionLeituraDep,
    filtros: FiltrosDep,
    janela: JanelaDep,
    pagina: Annotated[int, Query(ge=1, description="Página, começando em 1.")] = 1,
    tamanho_pagina: Annotated[
        int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Itens por página.")
    ] = 50,
) -> schemas.PaginaEstoque:
    try:
        resultado = service.listar_estoque(
            db, filtros, pagina=pagina, tamanho_pagina=tamanho_pagina, janela=janela
        )
    except service.EmpresaNaoEncontrada as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return schemas.PaginaEstoque(
        total=resultado.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(resultado.total / tamanho_pagina),
        atualizado_em=service.ultima_atualizacao(db),
        janela=_janela(janela),
        tem_vendas=resultado.tem_vendas,
        itens=[schemas.ItemEstoque.model_validate(i) for i in resultado.itens],
    )


@router.get(
    "/exportar",
    summary="Exporta o estoque filtrado em CSV (Excel)",
    description=(
        "Mesmos filtros e ordem da lista, sem paginação, até "
        f"{LIMITE_EXPORTACAO} linhas. `X-Total-Registros` traz o total encontrado."
    ),
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "Arquivo CSV."},
        404: {"model": Erro, "description": "Empresa não encontrada."},
    },
)
def exportar_estoque(
    db: SessionLeituraDep, settings: SettingsDep, filtros: FiltrosDep, janela: JanelaDep
) -> Response:
    try:
        resultado = service.listar_estoque(
            db, filtros, pagina=1, tamanho_pagina=LIMITE_EXPORTACAO, janela=janela
        )
    except service.EmpresaNaoEncontrada as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    linhas = (
        (
            i.id_produto,
            i.id_subproduto,
            i.descricao,
            i.fabricante,
            i.fornecedor,
            i.saldo_atual,
            i.saldo_reservado,
            i.saldo_disponivel,
            i.empresas_com_estoque,
            i.custo_gerencial,
            i.valor_custo,
            i.preco_varejo_min,
            i.preco_varejo_max,
            i.venda_media_diaria,
            i.cobertura_dias,
            ROTULOS_COBERTURA.get(i.status_cobertura or ""),
        )
        for i in resultado.itens
    )
    return resposta_csv(
        f"estoque_empresa_{filtros.empresa}" if filtros.empresa else "estoque_consolidado",
        (
            "Produto",
            "Subproduto",
            "Descrição",
            "Fabricante",
            "Último fornecedor",
            "Saldo atual",
            "Reservado",
            "Disponível",
            "Empresas com estoque",
            "Custo gerencial",
            "Valor em custo",
            "Preço varejo (mín.)",
            "Preço varejo (máx.)",
            f"Venda média/dia ({janela.dias} dias)",
            "Cobertura (dias)",
            "Classificação",
        ),
        linhas,
        tz=ZoneInfo(settings.tz),
        total=resultado.total,
    )


ROTULOS_COBERTURA = {
    "ruptura": "Ruptura",
    "critica": "Crítica",
    "baixa": "Baixa",
    "adequada": "Adequada",
    "excesso": "Excesso",
    "sem_giro": "Sem giro",
}


@router.get(
    "/cobertura",
    summary="Produtos em ruptura e por faixa de cobertura (dias de estoque)",
    description=(
        "Cobertura = saldo disponível / venda média diária da janela. Sem `empresa`: estoque "
        "e vendas da rede; com `empresa`, só dela (depósito, que não vende, vem zerado e "
        "com `tem_vendas` false)."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def resumo_cobertura(
    db: SessionLeituraDep,
    janela: JanelaDep,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
    local: Annotated[
        str | None,
        Query(
            description="Local de estoque (id_local_estoque); exige `empresa`. Inclui os "
            "locais somados a ele (ESTOQUE_LOCAIS_SOMADOS).",
            examples=["1"],
        ),
    ] = None,
    media: MediaDep = "vendas",
) -> schemas.ResumoCobertura:
    _exigir_empresa(local, empresa)
    try:
        r = service.contar_cobertura(db, janela, empresa, local, media)
    except service.EmpresaNaoEncontrada as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return schemas.ResumoCobertura(
        janela=_janela(janela),
        tem_vendas=r.tem_vendas,
        produtos=schemas.ContagemCobertura(**r.produtos),
    )


@router.get(
    "/cobertura/lojas",
    summary="Cobertura de cada empresa e de cada local de estoque dela",
    description=(
        "Para cada empresa ativa: a contagem da empresa inteira e a de cada local. A média é a "
        "da baixa real do estoque (o que a venda tirou do saldo no livro, menos as devoluções). "
        "O livro não diz de que local saiu: o saldo do local é comparado com a baixa da "
        "empresa, então locais que não vendem (trocas, avarias) mostram ruptura. "
        "Depósitos que não vendem vêm zerados e com `tem_vendas` false. Locais somados a "
        "outro (ESTOQUE_LOCAIS_SOMADOS, ex.: DEPOSITO 03 e 04 na LOJA MATRIZ) entram no "
        "saldo dele e vêm em `somados`. Os que não são de venda (ESTOQUE_LOCAIS_FORA_DA_LOJA: "
        "trocas, avarias...) ficam fora de tudo e vêm em `desconsiderados`. Ruptura, crítica "
        "e baixa só contam se um depósito de abastecimento tem saldo do item."
    ),
)
def cobertura_lojas(db: SessionLeituraDep, janela: JanelaDep) -> schemas.CoberturaLojas:
    return schemas.CoberturaLojas(
        janela=_janela(janela),
        empresas=[
            schemas.CoberturaEmpresa(
                empresa=EmpresaResumo.model_validate(e.empresa),
                tem_vendas=e.tem_vendas,
                produtos=schemas.ContagemCobertura(**e.produtos),
                excecoes=e.excecoes,
                desconsiderados=[
                    schemas.LocalSomado(id_local=i, descricao=d) for i, d in e.desconsiderados
                ],
                locais=[
                    schemas.CoberturaLocal(
                        id_local=x.id_local,
                        descricao=x.descricao,
                        produtos_com_saldo=x.produtos_com_saldo,
                        produtos=schemas.ContagemCobertura(**x.produtos),
                        somados=[
                            schemas.LocalSomado(id_local=i, descricao=d) for i, d in x.somados
                        ],
                    )
                    for x in e.locais
                ],
            )
            for e in service.cobertura_por_local(db, janela)
        ],
    )


AlvoDep = Annotated[
    int,
    Query(ge=7, le=120, description="Dias de venda que o pedido deve cobrir na loja."),
]


def _pedido(
    db: SessionLeituraDep, loja: str, janela: service.JanelaVendas, alvo_dias: int
) -> pedidos.PedidoAbastecimento:
    try:
        return pedidos.montar_pedido(db, loja, janela, alvo_dias)
    except service.EmpresaNaoEncontrada as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get(
    "/pedido-abastecimento",
    summary="Pedido de abastecimento da loja, separado por depósito",
    description=(
        "Itens da loja em ruptura, crítica ou baixa (como na aba Loja, sem as exceções) com o "
        "que falta para cobrir `alvo_dias` de venda. Cada item sai do depósito "
        "(ESTOQUE_DEPOSITOS_ABASTECIMENTO) com mais saldo; o resto, do outro. O que nenhum "
        "depósito tem vem em `sem_estoque`."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def pedido_abastecimento(
    db: SessionLeituraDep,
    janela: JanelaDep,
    loja: Annotated[str, Query(description="Código da loja.", examples=["1"])],
    alvo_dias: AlvoDep = pedidos.ALVO_PADRAO_DIAS,
) -> schemas.PedidoAbastecimento:
    p = _pedido(db, loja, janela, alvo_dias)
    return schemas.PedidoAbastecimento(
        loja=EmpresaResumo.model_validate(p.loja),
        janela=_janela(janela),
        alvo_dias=p.alvo_dias,
        tem_vendas=p.tem_vendas,
        pedidos=[
            schemas.PedidoDeposito(
                deposito=EmpresaResumo.model_validate(d.deposito),
                itens=[schemas.ItemPedidoAbastecimento.model_validate(i) for i in d.itens],
            )
            for d in p.pedidos
        ],
        sem_estoque=[schemas.ItemPedidoAbastecimento.model_validate(i) for i in p.sem_estoque],
    )


@router.get(
    "/pedido-abastecimento/exportar",
    summary="Exporta o pedido de abastecimento de um depósito em CSV (Excel)",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "Arquivo CSV."},
        404: {"model": Erro, "description": "Empresa ou depósito não encontrado."},
    },
)
def exportar_pedido_abastecimento(
    db: SessionLeituraDep,
    settings: SettingsDep,
    janela: JanelaDep,
    loja: Annotated[str, Query(description="Código da loja.", examples=["1"])],
    deposito: Annotated[str, Query(description="Código do depósito.", examples=["4"])],
    alvo_dias: AlvoDep = pedidos.ALVO_PADRAO_DIAS,
) -> Response:
    p = _pedido(db, loja, janela, alvo_dias)
    pedido = next((d for d in p.pedidos if d.deposito.codigo == deposito), None)
    if pedido is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"A empresa {deposito} não é depósito de abastecimento da loja {loja}.",
        )
    return resposta_csv(
        f"pedido_loja_{loja}_deposito_{deposito}",
        (
            "Marca",
            "Produto",
            "Subproduto",
            "Descrição",
            "Quantidade",
            "Saldo na loja",
            f"Venda média/dia ({janela.dias} dias)",
            "Cobertura (dias)",
            "Classificação",
            "Disponível no depósito",
        ),
        (
            (
                i.marca,
                i.id_produto,
                i.id_subproduto,
                i.descricao,
                i.quantidade,
                i.saldo_loja,
                i.venda_media_diaria,
                i.cobertura_dias,
                ROTULOS_COBERTURA.get(i.status_cobertura),
                i.disponivel_deposito,
            )
            for i in pedido.itens
        ),
        tz=ZoneInfo(settings.tz),
        total=len(pedido.itens),
    )


def _excecao(x: excecoes.Excecao) -> schemas.ExcecaoCobertura:
    return schemas.ExcecaoCobertura(
        empresa=EmpresaResumo.model_validate(x.empresa),
        id_produto=x.id_produto,
        id_subproduto=x.id_subproduto,
        descricao=x.descricao,
        motivo=x.motivo,
        usuario_nome=x.usuario_nome,
        criado_em=x.criado_em,
    )


@router.get(
    "/excecoes",
    summary="Exceções de falta por empresa",
    description=(
        "Produtos que não são falta na empresa (só ficam nos depósitos, ou a loja não tem "
        "estrutura para ter). Nela ficam sem classificação de cobertura (fora da ruptura, da "
        "crítica e da baixa) e fora do aviso de estoque baixo. Na rede continuam contando."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def listar_excecoes(
    db: SessionLeituraDep,
    empresa: Annotated[str | None, Query(description="Código da empresa.")] = None,
) -> list[schemas.ExcecaoCobertura]:
    da_empresa = empresa_por_codigo(db, empresa) if empresa else None
    return [_excecao(x) for x in excecoes.listar(db, da_empresa.id if da_empresa else None)]


@router.post(
    "/excecoes",
    summary="Inclui um item (ou a grade inteira) nas exceções de falta da empresa",
    responses={404: {"model": Erro, "description": "Empresa ou produto não encontrado."}},
)
def incluir_excecao(
    dados: schemas.NovaExcecaoCobertura, db: SessionDep, usuario: UsuarioAutenticadoDep
) -> schemas.ResultadoExcecaoCobertura:
    da_empresa = empresa_por_codigo(db, dados.empresa)
    try:
        novos = excecoes.incluir(
            db,
            da_empresa,
            dados.codigo,
            motivo=dados.motivo,
            usuario=usuario,
            agora=datetime.now(UTC),
        )
    except excecoes.ItemNaoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if novos:
        motivo = (dados.motivo or "").strip()
        atividades.registrar(
            db,
            "excecoes_alteradas",
            f"{usuario.nome_exibicao} incluiu {dados.codigo.strip()} nas exceções de falta "
            f"da empresa {dados.empresa}",
            usuario=usuario,
            detalhe=", ".join(s for _, s in novos) + (f" · {motivo}" if motivo else ""),
            empresas=[da_empresa.id],
        )
    db.commit()
    return schemas.ResultadoExcecaoCobertura(incluidos=len(novos))


@router.delete(
    "/excecoes/{empresa}/{id_produto}/{id_subproduto}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Tira o item das exceções de falta da empresa",
    responses={
        404: {"model": Erro, "description": "Empresa não encontrada ou item não é exceção."}
    },
)
def remover_excecao(
    empresa: Annotated[str, Path(max_length=20, description="Código da empresa.")],
    id_produto: Annotated[str, Path(max_length=50)],
    id_subproduto: Annotated[str, Path(max_length=50)],
    db: SessionDep,
    usuario: UsuarioAutenticadoDep,
) -> Response:
    da_empresa = empresa_por_codigo(db, empresa)
    if not excecoes.remover(db, da_empresa, id_produto, id_subproduto):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"O item {id_subproduto} não é exceção da empresa {empresa}.",
        )
    atividades.registrar(
        db,
        "excecoes_alteradas",
        f"{usuario.nome_exibicao} tirou {id_subproduto} das exceções de falta da empresa {empresa}",
        usuario=usuario,
        empresas=[da_empresa.id],
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


DIAS_LIVRO_PADRAO = 7
DIAS_EXTRATO_PADRAO = 30
DIAS_LIVRO_MAXIMO = 366

DIAS_MOVIMENTOS_PADRAO = 7


def _periodo_livro(
    settings: SettingsDep,
    data_inicial: date | None,
    data_final: date | None,
    padrao: int,
) -> tuple[Intervalo, date]:
    hoje = datetime.now(ZoneInfo(settings.tz)).date()
    try:
        periodo = intervalo_de("data_inicial", data_inicial, "data_final", data_final)
    except IntervaloInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    periodo = periodo or Intervalo(hoje - timedelta(days=padrao - 1), hoje)
    if periodo.inicio > hoje:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Período começa depois de hoje ({hoje.isoformat()}).",
        )
    if (periodo.fim - periodo.inicio).days >= DIAS_LIVRO_MAXIMO:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Período maior que {DIAS_LIVRO_MAXIMO} dias.",
        )
    return periodo, hoje


@router.get(
    "/livro",
    summary="Livro de movimentação: tudo o que entrou e saiu de cada loja, por COI",
    description=(
        "Todos os itens de nota do ERP (todos os COIs), com a categoria (venda, compra, "
        "transferência, perda...) e se o COI mexe no estoque (`afeta`). Sem datas: os "
        f"últimos {DIAS_LIVRO_PADRAO} dias. Período de até {DIAS_LIVRO_MAXIMO} dias."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa não encontrada."},
        422: {"model": Erro, "description": "Período inválido."},
    },
)
def livro_estoque(
    db: SessionLeituraDep,
    settings: SettingsDep,
    data_inicial: Annotated[date | None, Query(description="Primeiro dia (ERP).")] = None,
    data_final: Annotated[date | None, Query(description="Último dia, inclusive.")] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
    categoria: Annotated[
        schemas.CategoriaMovimento | None, Query(description="Só os COIs desta categoria.")
    ] = None,
) -> schemas.LivroEstoque:
    periodo, hoje = _periodo_livro(settings, data_inicial, data_final, DIAS_LIVRO_PADRAO)
    da_empresa = empresa_por_codigo(db, empresa) if empresa else None
    linhas = livro.resumo_livro(db, periodo, da_empresa, categoria)
    ate_hoje = Intervalo(periodo.inicio, min(periodo.fim, hoje))
    empresas = [da_empresa] if da_empresa else livro.empresas_ativas(db)
    return schemas.LivroEstoque(
        data_inicial=periodo.inicio,
        data_final=periodo.fim,
        linhas=[
            schemas.LinhaLivro(
                empresa=EmpresaResumo.model_validate(x.empresa),
                coi=x.coi,
                operacao=x.operacao,
                categoria=x.categoria,
                afeta=x.afeta,
                documentos=x.documentos,
                itens=x.itens,
                valor=x.valor,
            )
            for x in linhas
        ],
        dias_sem_leitura=sum(len(livro.dias_sem_leitura(db, e.id, ate_hoje)) for e in empresas),
    )


@router.get(
    "/livro/notas",
    summary="Documentos do livro: cada nota com data e hora, quem lançou, itens e valor",
    description=(
        "Um registro por documento (IDPLANILHA) e loja, do mais recente para o mais antigo. "
        "`momento` (data e hora) e `usuario` vêm do cabeçalho da nota: a saída traz os dois, "
        "a entrada só a hora, e os lançamentos sem nota (entrada e saída avulsa, balanço) "
        "nenhum. Filtros opcionais: período (sem datas: os últimos "
        f"{DIAS_LIVRO_PADRAO} dias), `empresa`, `categoria`, `coi` e `empresa_errada` (só as "
        "notas de saída, fora as transferências, com o CNPJ de outra empresa do grupo como "
        "destinatário)."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa não encontrada."},
        422: {"model": Erro, "description": "Período inválido."},
    },
)
def listar_notas_livro(
    db: SessionLeituraDep,
    settings: SettingsDep,
    data_inicial: Annotated[date | None, Query(description="Primeiro dia (ERP).")] = None,
    data_final: Annotated[date | None, Query(description="Último dia, inclusive.")] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
    categoria: Annotated[
        schemas.CategoriaMovimento | None, Query(description="Só os documentos desta categoria.")
    ] = None,
    coi: Annotated[int | None, Query(ge=0, description="Só os documentos deste COI.")] = None,
    empresa_errada: Annotated[
        bool, Query(description="Só as notas emitidas pela empresa errada.")
    ] = False,
    pagina: Annotated[int, Query(ge=1, description="Página, começando em 1.")] = 1,
    tamanho_pagina: Annotated[
        int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Documentos por página.")
    ] = 25,
) -> schemas.PaginaNotasLivro:
    periodo, _ = _periodo_livro(settings, data_inicial, data_final, DIAS_LIVRO_PADRAO)
    filtros = livro.FiltrosNotas(
        periodo=periodo,
        empresa=empresa_por_codigo(db, empresa) if empresa else None,
        categoria=categoria,
        coi=coi,
        empresa_errada=empresa_errada,
    )
    r = livro.listar_notas(db, filtros, pagina=pagina, tamanho_pagina=tamanho_pagina)
    return schemas.PaginaNotasLivro(
        total=r.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(r.total / tamanho_pagina),
        data_inicial=periodo.inicio,
        data_final=periodo.fim,
        notas=[
            schemas.NotaLivro(
                empresa=EmpresaResumo.model_validate(x.empresa),
                id_planilha=x.id_planilha,
                numero=x.numero,
                dia=x.dia,
                momento=x.momento,
                usuario=x.usuario,
                coi=x.coi,
                operacao=x.operacao,
                categoria=x.categoria,
                afeta=x.afeta,
                itens=x.itens,
                valor=x.valor,
                destinatario=x.destinatario,
                destino_empresa=x.destino_empresa,
                empresa_errada=x.empresa_errada,
            )
            for x in r.notas
        ],
    )


@router.get(
    "/livro/notas/{empresa}/{id_planilha}",
    summary="Produtos de um documento do livro",
    responses={404: {"model": Erro, "description": "Empresa ou documento não encontrado."}},
)
def itens_nota_livro(
    db: SessionLeituraDep,
    empresa: Annotated[str, Path(max_length=20, description="Código da empresa.")],
    id_planilha: Annotated[str, Path(max_length=50, description="Documento (IDPLANILHA).")],
) -> list[schemas.ItemNotaLivro]:
    itens = livro.itens_da_nota(db, empresa_por_codigo(db, empresa), id_planilha)
    if not itens:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Documento {id_planilha} sem itens na empresa {empresa}."
        )
    return [
        schemas.ItemNotaLivro(
            sequencia=x.movimento.sequencia,
            id_produto=x.movimento.id_produto,
            id_subproduto=x.movimento.id_subproduto,
            descricao=x.descricao,
            quantidade=x.movimento.quantidade,
            valor=x.movimento.valor,
        )
        for x in itens
    ]


DIAS_BALANCOS_PADRAO = 90


def _centavos(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), ROUND_HALF_UP)


def _totais_balanco(t: balancos.TotaisBalanco) -> dict[str, object]:
    return {
        "perda": _centavos(t.perda),
        "ganho": _centavos(t.ganho),
        "resultado": _centavos(t.resultado),
        "produtos_com_falta": t.produtos_com_falta,
        "produtos_com_sobra": t.produtos_com_sobra,
        "itens": t.itens,
        "balancos": t.balancos,
    }


def _ajuste(a: balancos.AjusteProduto) -> schemas.AjusteProduto:
    return schemas.AjusteProduto(
        empresa=EmpresaResumo.model_validate(a.empresa),
        id_produto=a.id_produto,
        id_subproduto=a.id_subproduto,
        descricao=a.descricao,
        quantidade=a.quantidade,
        valor=_centavos(a.valor),
    )


@router.get(
    "/balancos",
    summary="Balanços: perda, ganho, resultado por loja e prováveis transferências erradas",
    description=(
        "Ajustes dos itens de balanço (COI 2000) do período, a custo, como o relatório de "
        "balanço do ERP Poder: perda = soma dos ajustes negativos, ganho = dos positivos. "
        "`transferencias_provaveis`: o mesmo produto com falta numa loja e sobra em outra. "
        "Sem datas: os últimos "
        f"{DIAS_BALANCOS_PADRAO} dias; até {DIAS_LIVRO_MAXIMO}."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa não encontrada."},
        422: {"model": Erro, "description": "Período inválido."},
    },
)
def resumo_balancos(
    db: SessionLeituraDep,
    settings: SettingsDep,
    data_inicial: Annotated[date | None, Query(description="Primeiro dia (ERP).")] = None,
    data_final: Annotated[date | None, Query(description="Último dia, inclusive.")] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
) -> schemas.ResumoBalancos:
    periodo, _ = _periodo_livro(settings, data_inicial, data_final, DIAS_BALANCOS_PADRAO)
    da_empresa = empresa_por_codigo(db, empresa) if empresa else None
    r = balancos.resumo_balancos(db, periodo, da_empresa)
    eventos = movimentos.resumo_por_dia(
        db,
        movimentos.FiltrosMovimentos(
            periodo=periodo, empresa=da_empresa, tipo="balanco", sem_asterisco=True
        ),
    )
    return schemas.ResumoBalancos(
        data_inicial=periodo.inicio,
        data_final=periodo.fim,
        totais=schemas.TotaisBalanco(**_totais_balanco(r.totais)),
        por_loja=[
            schemas.LojaBalanco(
                empresa=EmpresaResumo.model_validate(loja.empresa),
                **_totais_balanco(loja.totais),
            )
            for loja in r.por_loja
        ],
        eventos=[_resumo_dia(e) for e in eventos],
        maiores_perdas=[_ajuste(a) for a in r.maiores_perdas],
        maiores_ganhos=[_ajuste(a) for a in r.maiores_ganhos],
        transferencias_provaveis=[
            schemas.ParTransferencia(
                id_produto=p.id_produto,
                id_subproduto=p.id_subproduto,
                descricao=p.descricao,
                loja_falta=EmpresaResumo.model_validate(p.falta.empresa),
                quantidade_falta=p.falta.quantidade,
                loja_sobra=EmpresaResumo.model_validate(p.sobra.empresa),
                quantidade_sobra=p.sobra.quantidade,
                quantidade=p.quantidade,
                valor=_centavos(p.valor),
            )
            for p in r.pares
        ],
        valor_transferencias_provaveis=_centavos(r.valor_pares),
        locais_perda=_locais_perda(db),
    )


@router.get(
    "/balancos/recontagens",
    summary="Produtos contados em mais de N balanços, ou recontados a partir de um dia",
    description=(
        "Por loja: produtos com itens em mais de `mais_de` documentos de balanço (COI 2000) "
        "no período. Com `desde`, só os recontados nesse dia ou depois (há uma contagem ali "
        "que não é a primeira do período); com `marca` (repetível), só dessas marcas. O ERP "
        "só lança o item com diferença. Sem "
        f"datas: os últimos {DIAS_BALANCOS_PADRAO} dias; até {DIAS_LIVRO_MAXIMO}."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa não encontrada."},
        422: {"model": Erro, "description": "Período inválido."},
    },
)
def recontagens_balanco(
    db: SessionLeituraDep,
    settings: SettingsDep,
    data_inicial: Annotated[date | None, Query(description="Primeiro dia (ERP).")] = None,
    data_final: Annotated[date | None, Query(description="Último dia, inclusive.")] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
    mais_de: Annotated[int, Query(ge=1, le=100, description="Contado em mais de N balanços.")] = 1,
    desde: Annotated[
        date | None, Query(description="Só os recontados nesse dia ou depois.")
    ] = None,
    marca: Annotated[
        list[str] | None,
        Query(description="Marca do produto; repita para várias (qualquer uma delas)."),
    ] = None,
) -> schemas.Recontagens:
    periodo, _ = _periodo_livro(settings, data_inicial, data_final, DIAS_BALANCOS_PADRAO)
    da_empresa = empresa_por_codigo(db, empresa) if empresa else None
    r = balancos.recontagens(
        db, periodo, mais_de=mais_de, desde=desde, empresa=da_empresa, marcas=marca or ()
    )
    return schemas.Recontagens(
        data_inicial=periodo.inicio,
        data_final=periodo.fim,
        mais_de=mais_de,
        desde=desde,
        total=r.total,
        limite=balancos.LIMITE_RECONTAGENS,
        itens=[
            schemas.Recontagem(
                empresa=EmpresaResumo.model_validate(x.empresa),
                id_produto=x.id_produto,
                id_subproduto=x.id_subproduto,
                descricao=x.descricao,
                marca=x.marca,
                contagens=x.contagens,
                dias=list(x.dias),
                quantidade=x.quantidade,
                valor=_centavos(x.valor),
            )
            for x in r.itens
        ],
        marcas=[schemas.MarcaRecontagem(marca=nome, produtos=n) for nome, n in r.marcas],
    )


def _justificativa(j: JustificativaAvulsa) -> schemas.JustificativaAvulsa:
    return schemas.JustificativaAvulsa(
        motivo=j.motivo,
        motivo_rotulo=(
            justificativas.POR_CODIGO[j.motivo].rotulo
            if j.motivo in justificativas.POR_CODIGO
            else j.motivo
        ),
        observacao=j.observacao,
        usuario_nome=j.usuario_nome,
        atualizado_em=j.updated_at,
        pelo_vinculo=j.pelo_vinculo,
    )


def _vinculo(v: justificativas.Vinculo) -> schemas.VinculoAvulsa:
    return schemas.VinculoAvulsa(
        id_planilha=v.id_planilha,
        dia=v.dia,
        tipo=v.tipo,
        usuario_nome=v.usuario_nome,
        criado_em=v.criado_em,
    )


def _pendencias(p: justificativas.Pendencias) -> schemas.PendenciasAvulsas:
    return schemas.PendenciasAvulsas(documentos=p.documentos, valor=_centavos(p.valor))


@router.get(
    "/avulsas/documentos",
    summary="Entradas e saídas avulsas por documento, com a justificativa de cada uma",
    description=(
        "Um registro por documento avulso (COI 80 ou 8080). `situacao`: `pendente` (sem "
        "justificativa; com `JUSTIFICAR_AVULSAS_DESDE`, só do dia de corte em diante), "
        "`justificada` ou `todas`. `alerta`: só as entradas com o aviso dessa regra "
        f"(`regras` da resposta). Sem datas: os últimos {DIAS_MOVIMENTOS_PADRAO} dias; até "
        f"{DIAS_LIVRO_MAXIMO}."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa não encontrada."},
        422: {"model": Erro, "description": "Período ou regra inválidos."},
    },
)
def documentos_avulsos(
    db: SessionLeituraDep,
    settings: SettingsDep,
    data_inicial: Annotated[date | None, Query(description="Primeiro dia (ERP).")] = None,
    data_final: Annotated[date | None, Query(description="Último dia, inclusive.")] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
    tipo: Annotated[justificativas.TipoAvulsa | None, Query(description="Só um tipo.")] = None,
    situacao: Annotated[justificativas.Situacao, Query()] = "pendente",
    alerta: Annotated[
        str | None, Query(max_length=30, description="Só as entradas com o aviso dessa regra.")
    ] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanho_pagina: Annotated[int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO)] = 50,
) -> schemas.PaginaDocumentosAvulsos:
    if alerta is not None and alerta not in justificativas.REGRAS_POR_CODIGO:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Regra {alerta!r} não existe.")
    periodo, _ = _periodo_livro(settings, data_inicial, data_final, DIAS_MOVIMENTOS_PADRAO)
    da_empresa = empresa_por_codigo(db, empresa) if empresa else None
    corte = justificativas.corte(db, settings.justificar_avulsas_desde)
    desde = corte.dia
    r = justificativas.listar_documentos(
        db,
        periodo=periodo,
        desde=desde,
        empresa=da_empresa,
        tipo=tipo,
        situacao=situacao,
        alerta=alerta,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
    )
    return schemas.PaginaDocumentosAvulsos(
        data_inicial=periodo.inicio,
        data_final=periodo.fim,
        justificar_desde=desde,
        situacao=situacao,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total=r.total,
        total_paginas=ceil(r.total / tamanho_pagina) if r.total else 0,
        documentos=[
            schemas.DocumentoAvulso(
                empresa=EmpresaResumo.model_validate(x.empresa),
                id_planilha=x.id_planilha,
                dia=x.dia,
                tipo=x.tipo,
                itens=x.itens,
                quantidade=x.quantidade,
                valor=_centavos(x.valor),
                id_produto=x.id_produto,
                id_subproduto=x.id_subproduto,
                descricao=x.descricao,
                exige_justificativa=x.exige,
                justificativa=_justificativa(x.justificativa) if x.justificativa else None,
                vinculo=_vinculo(x.vinculo) if x.vinculo else None,
                alertas=[
                    schemas.AlertaAvulsa(
                        regra=a.regra,
                        id_produto=a.id_produto,
                        id_subproduto=a.id_subproduto,
                        descricao=a.descricao,
                        dia=a.dia,
                        id_planilha=a.id_planilha,
                        numero=a.numero,
                        operacao=a.operacao,
                        quantidade=a.quantidade,
                        valor=_centavos(a.valor),
                    )
                    for a in x.alertas
                ],
            )
            for x in r.documentos
        ],
        pendentes=_pendencias(r.pendentes),
        pendentes_desde_o_corte=_pendencias(r.pendentes_desde_o_corte),
        justificadas=r.justificadas,
        motivos=[
            schemas.MotivoAvulsa(
                codigo=m.codigo,
                rotulo=m.rotulo,
                tipos=list(m.tipos),
                exige_observacao=m.codigo in justificativas.MOTIVOS_COM_OBSERVACAO,
            )
            for m in justificativas.MOTIVOS
        ],
        regras=[
            schemas.RegraAlerta(codigo=r.codigo, rotulo=r.rotulo, janela_dias=r.janela_dias)
            for r in justificativas.REGRAS
        ],
        corte=_corte(corte),
    )


def _corte(c: justificativas.Corte) -> schemas.CorteAvulsas:
    return schemas.CorteAvulsas(
        justificar_desde=c.dia, definido_por=c.usuario_nome, atualizado_em=c.atualizado_em
    )


@router.get("/avulsas/corte", summary="Dia de corte das justificativas das avulsas")
def corte_avulsas(db: SessionLeituraDep, settings: SettingsDep) -> schemas.CorteAvulsas:
    return _corte(justificativas.corte(db, settings.justificar_avulsas_desde))


@router.put(
    "/avulsas/corte",
    summary="Muda o dia de corte das justificativas (ADMIN)",
    description=(
        "Avulsas desse dia em diante ficam pendentes até alguém justificar; `null`: todas. "
        "Substitui `JUSTIFICAR_AVULSAS_DESDE` do .env e vale na hora, sem reiniciar."
    ),
)
def definir_corte_avulsas(
    dados: schemas.NovoCorteAvulsas, db: SessionDep, admin: AdminDep
) -> schemas.CorteAvulsas:
    c = justificativas.definir_corte(
        db,
        dados.justificar_desde,
        usuario_id=admin.id,
        usuario_nome=admin.nome_exibicao,
        agora=datetime.now(UTC),
    )
    dia = f"{dados.justificar_desde:%d/%m/%Y}" if dados.justificar_desde else "nenhum"
    atividades.registrar(
        db,
        "avulsas_alteradas",
        f"{admin.nome_exibicao} mudou o dia de corte das avulsas para {dia}",
        usuario=admin,
    )
    db.commit()
    return _corte(c)


@router.put(
    "/avulsas/justificativas",
    summary="Justifica várias entradas ou saídas avulsas de uma vez",
    description=(
        "A mesma justificativa (motivo e observação) em todos os documentos, até "
        f"{justificativas.LIMITE_LOTE}. O motivo tem que valer para o tipo de cada um. Tudo ou "
        "nada: com um documento inválido, nenhum é gravado."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa ou documento avulso não encontrado."},
        422: {"model": Erro, "description": "Motivo inválido ou observação faltando."},
    },
)
def justificar_avulsas_em_lote(
    dados: schemas.JustificativaEmLote,
    db: SessionDep,
    usuario: UsuarioAutenticadoDep,
) -> schemas.ResultadoLoteJustificativas:

    empresas = {x.empresa: empresa_por_codigo(db, x.empresa) for x in dados.documentos}
    try:
        registros = justificativas.justificar_varios(
            db,
            [(empresas[x.empresa], x.id_planilha) for x in dados.documentos],
            motivo=dados.motivo,
            observacao=dados.observacao,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome_exibicao,
            agora=datetime.now(UTC),
        )
    except justificativas.JustificativaInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except justificativas.DocumentoNaoAvulso as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    atividades.registrar(
        db,
        "avulsas_alteradas",
        f"{usuario.nome_exibicao} justificou {len(registros)} avulsas de uma vez",
        usuario=usuario,
        detalhe=f"Motivo: {dados.motivo}" + (f" · {dados.observacao}" if dados.observacao else ""),
        empresas=[e.id for e in empresas.values()],
    )
    db.commit()
    return schemas.ResultadoLoteJustificativas(justificados=len(registros))


@router.put(
    "/avulsas/{empresa}/{id_planilha}/justificativa",
    summary="Justifica (ou corrige a justificativa de) uma entrada ou saída avulsa",
    description=(
        "Grava o motivo (um dos `motivos` da lista, que valha para o tipo do documento) e a "
        "observação, obrigatória no motivo `outro`. Substitui a anterior; fica quem justificou."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa ou documento avulso não encontrado."},
        422: {"model": Erro, "description": "Motivo inválido ou observação faltando."},
    },
)
def justificar_avulsa(
    empresa: Annotated[str, Path(max_length=20, description="Código da empresa.")],
    id_planilha: Annotated[str, Path(max_length=50, description="Documento (IDPLANILHA).")],
    dados: schemas.NovaJustificativaAvulsa,
    db: SessionDep,
    usuario: UsuarioAutenticadoDep,
) -> schemas.JustificativaAvulsa:
    da_empresa = empresa_por_codigo(db, empresa)
    try:
        registro = justificativas.justificar(
            db,
            da_empresa,
            id_planilha,
            motivo=dados.motivo,
            observacao=dados.observacao,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome_exibicao,
            agora=datetime.now(UTC),
        )
    except justificativas.JustificativaInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if registro is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Documento {id_planilha} não é uma entrada ou saída avulsa da empresa {empresa}.",
        )
    atividades.registrar(
        db,
        "avulsas_alteradas",
        f"{usuario.nome_exibicao} justificou a avulsa {id_planilha} da empresa {empresa}",
        usuario=usuario,
        detalhe=f"Motivo: {dados.motivo}" + (f" · {dados.observacao}" if dados.observacao else ""),
        empresas=[da_empresa.id],
    )
    db.commit()
    return _justificativa(registro)


EmpresaPath = Annotated[str, Path(max_length=20, description="Código da empresa.")]
DocumentoPath = Annotated[str, Path(max_length=50, description="Documento (IDPLANILHA).")]


@router.get(
    "/avulsas/{empresa}/{id_planilha}/candidatos",
    summary="Avulsas do outro tipo que podem ser o par do documento",
    description=(
        "Mesma loja, algum produto em comum, até "
        f"{justificativas.JANELA_CANDIDATOS_DIAS} dias antes ou depois e ainda sem vínculo. "
        "Primeiro as exatas (mesmos produtos e quantidades)."
    ),
    responses={404: {"model": Erro, "description": "Empresa ou documento avulso não encontrado."}},
)
def candidatos_vinculo(
    empresa: EmpresaPath, id_planilha: DocumentoPath, db: SessionLeituraDep
) -> list[schemas.CandidatoVinculo]:
    lista = justificativas.candidatos(db, empresa_por_codigo(db, empresa), id_planilha)
    if lista is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Documento {id_planilha} não é uma entrada ou saída avulsa da empresa {empresa}.",
        )
    return [
        schemas.CandidatoVinculo(
            id_planilha=c.id_planilha,
            dia=c.dia,
            tipo=c.tipo,
            itens=c.itens,
            quantidade=c.quantidade,
            valor=_centavos(c.valor),
            em_comum=c.em_comum,
            exato=c.exato,
            id_produto=c.id_produto,
            id_subproduto=c.id_subproduto,
            descricao=c.descricao,
            justificativa=_justificativa(c.justificativa) if c.justificativa else None,
        )
        for c in lista
    ]


@router.put(
    "/avulsas/{empresa}/{id_planilha}/vinculo",
    summary="Relaciona uma entrada avulsa com uma saída avulsa da mesma loja",
    description=(
        "Um com um. Justifica os dois documentos que ainda não tinham justificativa como "
        "correção de lançamento (`pelo_vinculo`)."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa ou documento avulso não encontrado."},
        409: {"model": Erro, "description": "Um dos documentos já está relacionado."},
        422: {"model": Erro, "description": "Os dois documentos são do mesmo tipo."},
    },
)
def relacionar_avulsas(
    empresa: EmpresaPath,
    id_planilha: DocumentoPath,
    dados: schemas.NovoVinculoAvulsa,
    db: SessionDep,
    usuario: UsuarioAutenticadoDep,
) -> schemas.VinculoAvulsa:
    da_empresa = empresa_por_codigo(db, empresa)
    try:
        vinculo = justificativas.relacionar(
            db,
            da_empresa,
            id_planilha,
            dados.id_planilha,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome_exibicao,
            agora=datetime.now(UTC),
        )
    except justificativas.JaRelacionado as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except justificativas.VinculoInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if vinculo is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Os documentos {id_planilha} e {dados.id_planilha} precisam ser avulsas da "
            f"empresa {empresa}.",
        )
    atividades.registrar(
        db,
        "avulsas_alteradas",
        f"{usuario.nome_exibicao} relacionou as avulsas {id_planilha} e {dados.id_planilha}"
        f" da empresa {empresa}",
        usuario=usuario,
        empresas=[da_empresa.id],
    )
    db.commit()
    par = justificativas.par_do_documento(db, da_empresa, id_planilha)
    if par is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "O vínculo foi desfeito em seguida.")
    return _vinculo(par)


@router.delete(
    "/avulsas/{empresa}/{id_planilha}/vinculo",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desfaz o vínculo do documento (e as justificativas que ele criou)",
    responses={404: {"model": Erro, "description": "Documento sem vínculo."}},
)
def desfazer_vinculo_avulsas(
    empresa: EmpresaPath,
    id_planilha: DocumentoPath,
    db: SessionDep,
    usuario: UsuarioAutenticadoDep,
) -> Response:
    da_empresa = empresa_por_codigo(db, empresa)
    if not justificativas.desfazer_vinculo(db, da_empresa, id_planilha):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Documento {id_planilha} não está relacionado."
        )
    atividades.registrar(
        db,
        "avulsas_alteradas",
        f"{usuario.nome_exibicao} desfez o vínculo da avulsa {id_planilha} da empresa {empresa}",
        usuario=usuario,
        empresas=[da_empresa.id],
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/fornecedores", summary="Fornecedores das compras, para o filtro da lista")
def listar_fornecedores(db: SessionLeituraDep) -> list[schemas.FornecedorEstoque]:
    return [schemas.FornecedorEstoque.model_validate(f) for f in service.listar_fornecedores(db)]


@router.get("/resumo", summary="Totais do estoque, última atualização e números por empresa")
def resumo_estoque(db: SessionLeituraDep) -> schemas.ResumoEstoque:
    r = service.resumo_estoque(db)
    return schemas.ResumoEstoque(
        produtos=r.produtos,
        produtos_com_saldo=r.produtos_com_saldo,
        produtos_negativos=r.produtos_negativos,
        produtos_com_reserva=r.produtos_com_reserva,
        atualizado_em=r.atualizado_em,
        ultima_sincronizacao=(
            schemas.UltimaSincronizacao.model_validate(r.ultima_sincronizacao)
            if r.ultima_sincronizacao
            else None
        ),
        por_empresa=[
            schemas.EstoquePorEmpresa(
                empresa=EmpresaResumo.model_validate(e.empresa),
                produtos_com_saldo=e.produtos_com_saldo,
                linhas=e.linhas,
                valor_custo=e.valor_custo,
            )
            for e in r.por_empresa
        ],
        valor_custo=r.valor_custo,
        linhas_sem_custo=r.linhas_sem_custo,
        precos_atualizados_em=r.precos_atualizados_em,
        locais_perda=_locais_perda(db),
    )


def _locais_perda(db: SessionLeituraDep) -> list[schemas.LocalPerda]:
    return [
        schemas.LocalPerda(
            empresa=EmpresaResumo.model_validate(x.empresa),
            id_local=x.id_local,
            descricao=x.descricao,
            motivo=x.motivo,
            produtos=x.produtos,
            valor=_centavos(x.valor) if x.valor is not None else None,
        )
        for x in service.resumo_locais_perda(db)
    ]


@router.get(
    "/movimentos",
    summary="Lista entradas e saídas avulsas e balanços, com resumo por empresa e dia",
    description=(
        "Itens de entrada avulsa (COI 80), saída avulsa (COI 8080) e balanço (COI 2000) "
        "lidos do ERP. `quantidade` e `valor` são o efeito no estoque: entrada e sobra "
        "positivas, saída e falta negativas.\n\n"
        "Filtros opcionais: `data_inicial`/`data_final` (dias no fuso do ERP, inclusivos, "
        "os dois juntos), `empresa`, `tipo`, `produto` e `subproduto` (códigos exatos). "
        f"Sem período: os últimos {DIAS_MOVIMENTOS_PADRAO} dias; período de até "
        f"{DIAS_LIVRO_MAXIMO} dias. Lista do mais recente para o mais antigo; "
        "`resumo` traz um registro por empresa, dia e tipo, com falta e sobra do balanço "
        "em separado."
    ),
    responses={404: {"model": Erro, "description": "Empresa não encontrada."}},
)
def listar_movimentos(
    db: SessionLeituraDep,
    settings: SettingsDep,
    data_inicial: Annotated[date | None, Query(description="Início do período.")] = None,
    data_final: Annotated[date | None, Query(description="Fim do período, inclusive.")] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["1"])] = None,
    tipo: Annotated[
        movimentos.FiltroTipo | None,
        Query(description="entrada_avulsa, saida_avulsa, balanco ou avulsas (as duas avulsas)."),
    ] = None,
    produto: Annotated[
        str | None, Query(max_length=50, description="Código exato do produto.", examples=["9798"])
    ] = None,
    subproduto: Annotated[
        str | None, Query(max_length=50, description="Código exato do subproduto.")
    ] = None,
    pagina: Annotated[int, Query(ge=1, description="Página, começando em 1.")] = 1,
    tamanho_pagina: Annotated[
        int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Itens por página.")
    ] = 50,
) -> schemas.PaginaMovimentosEstoque:

    periodo, _ = _periodo_livro(settings, data_inicial, data_final, DIAS_MOVIMENTOS_PADRAO)
    filtros = movimentos.FiltrosMovimentos(
        periodo=periodo,
        empresa=empresa_por_codigo(db, empresa) if empresa else None,
        tipo=tipo,
        produto=produto.strip() or None if produto else None,
        subproduto=subproduto.strip() or None if subproduto else None,
    )
    pagina_ = movimentos.listar_movimentos(
        db, filtros, pagina=pagina, tamanho_pagina=tamanho_pagina
    )
    cobertura = movimentos.cobertura(db)
    return schemas.PaginaMovimentosEstoque(
        total=pagina_.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(pagina_.total / tamanho_pagina),
        filtro=schemas.FiltroMovimentos(
            data_inicial=periodo.inicio,
            data_final=periodo.fim,
            empresa=EmpresaResumo.model_validate(filtros.empresa) if filtros.empresa else None,
            tipo=tipo,
            produto=filtros.produto,
            subproduto=filtros.subproduto,
        ),
        cobertura=schemas.CoberturaMovimentos(
            desde=cobertura.desde, ate=cobertura.ate, atualizado_em=cobertura.atualizado_em
        ),
        itens=[
            schemas.MovimentoEstoque(
                id=linha.movimento.id,
                empresa=EmpresaResumo.model_validate(linha.empresa),
                dia=linha.movimento.dia,
                tipo=cast(schemas.TipoMovimento, linha.movimento.tipo),
                coi=linha.movimento.coi,
                id_planilha=linha.movimento.id_planilha,
                sequencia=linha.movimento.sequencia,
                id_produto=linha.movimento.id_produto,
                id_subproduto=linha.movimento.id_subproduto,
                descricao=linha.descricao,
                quantidade=linha.movimento.quantidade,
                valor=linha.movimento.valor,
            )
            for linha in pagina_.itens
        ],
        resumo=[_resumo_dia(r) for r in movimentos.resumo_por_dia(db, filtros)],
    )


def _resumo_dia(r: movimentos.ResumoDia) -> schemas.ResumoMovimentosDia:
    balanco = r.tipo == "balanco"
    return schemas.ResumoMovimentosDia(
        empresa=EmpresaResumo.model_validate(r.empresa),
        dia=r.dia,
        tipo=r.tipo,
        itens=r.itens,
        quantidade=r.quantidade,
        valor=r.valor,
        falta_itens=r.falta_itens if balanco else None,
        falta_quantidade=r.falta_quantidade if balanco else None,
        falta_valor=r.falta_valor if balanco else None,
        sobra_itens=r.sobra_itens if balanco else None,
        sobra_quantidade=r.sobra_quantidade if balanco else None,
        sobra_valor=r.sobra_valor if balanco else None,
    )


@router.get(
    "/{id_produto}/{id_subproduto}",
    summary="Detalha um produto: saldo consolidado, por empresa e por local",
    responses={404: {"model": Erro, "description": "Produto sem estoque registrado."}},
)
def detalhar_produto(
    db: SessionLeituraDep,
    janela: JanelaDep,
    id_produto: Annotated[str, Path(max_length=50, examples=["9798"])],
    id_subproduto: Annotated[str, Path(max_length=50, examples=["9798"])],
) -> schemas.ProdutoEstoque:
    produto = service.detalhar_produto(db, id_produto, id_subproduto, janela)
    if produto is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Produto {id_produto}/{id_subproduto} sem estoque registrado.",
        )
    return schemas.ProdutoEstoque(
        id_produto=produto.detalhe.id_produto,
        id_subproduto=produto.detalhe.id_subproduto,
        descricao=service.texto_descricao(produto.detalhe.produto),
        fabricante=produto.detalhe.produto.marca if produto.detalhe.produto else None,
        saldo_atual=produto.saldo_atual,
        saldo_reservado=produto.saldo_reservado,
        saldo_disponivel=produto.saldo_disponivel,
        venda_media_diaria=_media(produto.venda_media_diaria),
        cobertura_dias=produto.cobertura_dias,
        status_cobertura=produto.status_cobertura,
        empresas_com_estoque=produto.empresas_com_estoque,
        atualizado_em=produto.atualizado_em,
        empresas=[
            schemas.EmpresaDoProduto(
                empresa=EmpresaResumo.model_validate(e.empresa),
                saldo_atual=e.saldo_atual,
                saldo_reservado=e.saldo_reservado,
                saldo_disponivel=e.saldo_disponivel,
                venda_media_diaria=_media(e.venda_media_diaria),
                cobertura_dias=e.cobertura_dias,
                status_cobertura=e.status_cobertura,
                preco=schemas.PrecoEmpresa.model_validate(e.preco) if e.preco else None,
                valor_custo=e.valor_custo,
                locais=[
                    schemas.LocalEstoque.model_validate(linha).model_copy(update={"perda": perda})
                    for linha, perda in e.locais
                ],
            )
            for e in produto.empresas
        ],
        fornecedores=[
            schemas.FornecedorDoProduto(
                nome=f.nome,
                cnpj=f.cnpj,
                compras=f.compras,
                quantidade=f.quantidade,
                ultima_compra=f.ultima_compra,
                ultima_empresa=EmpresaResumo.model_validate(f.ultima_empresa),
                custo_ultima=f.custo_ultima,
            )
            for f in produto.fornecedores
        ],
        janela=_janela(janela),
    )


def _media(valor: Decimal | None) -> Decimal | None:
    return valor.quantize(Decimal("0.001"), ROUND_HALF_UP) if valor is not None else None


@router.get(
    "/{id_produto}/{id_subproduto}/extrato",
    summary="Extrato do produto numa loja: entradas, saídas e saldo no fim de cada dia",
    description=(
        "Todos os movimentos do produto na empresa (todos os COIs). O saldo é reconstruído "
        "a partir do saldo atual, de trás para frente, só com os COIs que mexem no estoque; "
        "`dias_sem_leitura` diz se falta algum dia do livro. Sem datas: os últimos "
        f"{DIAS_EXTRATO_PADRAO} dias."
    ),
    responses={
        404: {"model": Erro, "description": "Empresa não encontrada."},
        422: {"model": Erro, "description": "Período inválido."},
    },
)
def extrato_produto(
    db: SessionLeituraDep,
    settings: SettingsDep,
    id_produto: Annotated[str, Path(max_length=50, examples=["10390"])],
    id_subproduto: Annotated[str, Path(max_length=50, examples=["28904"])],
    empresa: Annotated[str, Query(description="Código da empresa.", examples=["1"])],
    data_inicial: Annotated[date | None, Query(description="Primeiro dia (ERP).")] = None,
    data_final: Annotated[date | None, Query(description="Último dia, inclusive.")] = None,
) -> schemas.ExtratoProduto:
    periodo, hoje = _periodo_livro(settings, data_inicial, data_final, DIAS_EXTRATO_PADRAO)
    x = livro.extrato(db, empresa_por_codigo(db, empresa), id_produto, id_subproduto, periodo, hoje)
    return schemas.ExtratoProduto(
        empresa=EmpresaResumo.model_validate(x.empresa),
        id_produto=id_produto,
        id_subproduto=id_subproduto,
        descricao=service.descricao_do_produto(db, id_produto, id_subproduto),
        data_inicial=periodo.inicio,
        data_final=periodo.fim,
        saldo_atual=x.saldo_atual,
        saldo_inicial=x.saldo_inicial,
        saldo_final=x.saldo_final,
        entradas=x.entradas,
        saidas=x.saidas,
        por_categoria=[
            schemas.TotalCategoriaExtrato(
                categoria=t.categoria, afeta=t.afeta, itens=t.itens, quantidade=t.quantidade
            )
            for t in x.por_categoria
        ],
        total_itens=x.total_itens,
        limite=livro.LIMITE_EXTRATO,
        itens=[
            schemas.MovimentoExtrato(
                dia=linha.movimento.dia,
                coi=linha.movimento.coi,
                operacao=(linha.movimento.operacao or "").strip() or None,
                categoria=cast(schemas.CategoriaMovimento, linha.movimento.tipo),
                afeta=linha.afeta,
                id_planilha=linha.movimento.id_planilha,
                sequencia=linha.movimento.sequencia,
                quantidade=linha.movimento.quantidade,
                valor=linha.movimento.valor,
                saldo_fim_dia=linha.saldo_fim_dia,
            )
            for linha in x.itens
        ],
        dias_sem_leitura=list(x.dias_sem_leitura),
    )
