from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select

from app.core.config import get_settings
from app.database.models import Empresa, Produto, Vendedor
from app.erp.servicos import ItemNota, Nota, Recebimento
from app.services import vendas as service
from app.sync.vendas import _gravar_dia
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

URL = "/api/v1/vendas/resumo"
AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _nota(planilha: str, *, cancelada: bool = False) -> Nota:
    return Nota(
        id_empresa="",
        id_planilha=planilha,
        numero=planilha,
        serie="1",
        chave_nfe=None,
        cnpj_cpf=None,
        data_emissao=AGORA,
        data_movimento=AGORA,
        cancelada=cancelada,
        data_alteracao=AGORA,
        modelo="65",
    )


def _item(
    planilha: str, coi: int, produto: str, valor: str, qtd: str = "1", vendedor: str | None = None
) -> ItemNota:
    return ItemNota(
        id_empresa="",
        id_planilha=planilha,
        id_operacao=coi,
        id_produto=produto,
        id_subproduto=produto,
        sequencia=produto,
        quantidade=Decimal(qtd),
        descricao_produto=f"PRODUTO {produto}",
        data_movimento=AGORA,
        valor_liquido=Decimal(valor),
        valor_desconto=Decimal("0"),
        id_vendedor=vendedor,
    )


def _venda(
    planilha: str,
    coi: int,
    *itens: tuple[str, str, str],
    cancelada: bool = False,
    vendedor: str | None = None,
):
    return _nota(planilha, cancelada=cancelada), [
        _item(planilha, coi, p, v, q, vendedor) for p, v, q in itens
    ]


def _titulos(
    *parcelas: tuple[str, tuple[int, str], str, date, str, date | None],
    juros: str = "0",
) -> dict[tuple[str, str, str], Recebimento]:
    titulos = {}
    for planilha, (id_forma, forma), valor, lancamento, pago, pago_em in parcelas:
        titulos[(planilha, "1", "1")] = Recebimento(
            id_empresa="",
            id_planilha=planilha,
            id_titulo="1",
            parcela="1",
            serie="PDV",
            id_forma=id_forma,
            forma=forma,
            valor=Decimal(valor),
            data_movimento=None,
            valor_pago=Decimal(pago),
            valor_pendente=Decimal(valor) - Decimal(pago),
            juros=Decimal(juros),
            dia_lancamento=lancamento,
            dia_pagamento=pago_em,
        )
    return titulos


PIX = (8, "PIX TEF")
DEBITO = (5, "CARTAO DEBITO TEF")
BOLETO = (63, "BOLETO BANCO")
D1, D2 = date(2026, 10, 1), date(2026, 10, 2)


@pytest.fixture
def vendas_db(db_vazio):
    db = db_vazio
    empresas = {}
    for codigo in ("1", "2"):
        empresas[codigo] = Empresa(id_erp=codigo, codigo=codigo, nome=f"Loja {codigo}")
        db.add(empresas[codigo])
    for produto, divisao in (("10", "TINTAS"), ("20", "HIDRAULICA")):
        db.add(
            Produto(
                id_produto=produto,
                id_subproduto=produto,
                descricao=f"CADASTRO {produto}",
                divisao=divisao,
                sincronizado_em=AGORA,
            )
        )
    db.flush()

    dias = {
        ("1", date(2026, 9, 2)): [_venda("1", 8300, ("10", "50.00", "2"), vendedor="7")],
        ("1", date(2026, 10, 1)): [
            _venda("2", 8300, ("10", "100.00", "4"), ("20", "20.00", "1"), vendedor="7"),
            _venda("3", 3001, ("20", "500.00", "10"), vendedor="8"),
            _venda("4", 8300, ("10", "999.00", "1"), cancelada=True, vendedor="9"),
        ],
        ("2", date(2026, 10, 2)): [_venda("5", 8001, ("99", "80.00", "3"))],
        ("1", date(2026, 10, 2)): [],
    }
    extras = {
        ("1", D1): {
            "titulos": _titulos(
                ("T1", PIX, "200.00", D1, "200.00", D1),
                ("T2", PIX, "100.00", D1, "100.00", D1),
                ("T3", PIX, "100.00", D1, "100.00", D1),
                ("T4", DEBITO, "110.00", D1, "110.00", D1),
                ("T5", DEBITO, "110.00", D1, "0", None),
            ),
            "devolucoes": [_venda("D1", 31, ("10", "30.00", "1"))],
        },
        ("1", D2): {
            "titulos_pagos": _titulos(
                ("B1", BOLETO, "50.00", date(2026, 8, 15), "50.00", D2), juros="2.50"
            )
        },
        ("2", D2): {"titulos": _titulos(("T6", PIX, "80.00", D2, "80.00", D2))},
    }
    for (codigo, dia), notas in dias.items():
        _gravar_dia(
            db,
            empresas[codigo].id,
            dia,
            notas,
            completo=True,
            execucao_id=None,
            momento=AGORA,
            **extras.get((codigo, dia), {}),
        )
    db.flush()
    return db


@pytest.fixture
def api_vendas(vendas_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.vendas", "OPERADOR", modulos=["VENDAS"])
    app = app_com_sessao(vendas_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_sem_token_401(client):
    assert client.get(URL).status_code == 401


def test_sem_modulo_vendas_403(db_vazio, criar_usuario_teste):
    operador = criar_usuario_teste("op.sem.vendas", "OPERADOR", modulos=["DASHBOARD"])
    app = app_com_sessao(db_vazio)
    assert TestClient(app, headers=token_para(app, operador)).get(URL).status_code == 403


def test_sem_periodo_soma_tudo_menos_cancelada_e_serie_por_mes(api_vendas):
    corpo = api_vendas.get(URL).json()

    assert corpo["totais"] == {
        "faturamento": "750.00",
        "notas": 4,
        "ticket_medio": "187.50",
        "quantidade": "20.0000",
        "desconto": "0.00",
        "devolucoes": "30.00",
        "faturamento_liquido": "720.00",
    }
    assert corpo["comparacao"] is None
    assert corpo["formas_pagamento"] == [
        {"forma": "PIX TEF", "valor": "480.00", "parcelas": 4},
        {"forma": "CARTAO DEBITO TEF", "valor": "220.00", "parcelas": 2},
        {"forma": "BOLETO BANCO", "valor": "50.00", "parcelas": 1},
    ]
    assert "recebidos" not in corpo
    assert corpo["granularidade"] == "mes"
    assert [(p["chave"], p["faturamento"], p["notas"]) for p in corpo["serie"]] == [
        ("2026-09", "50.00", 1),
        ("2026-10", "700.00", 3),
    ]
    assert [(c["canal"], c["rotulo"], c["faturamento"]) for c in corpo["por_canal"]] == [
        ("faturamento", "Faturamento logística", "500.00"),
        ("balcao", "Balcão (NFC-e)", "170.00"),
        ("televendas", "Televendas", "80.00"),
    ]
    assert corpo["cobertura"] == {
        "desde": "2026-10-02",
        "ate": "2026-10-02",
        "atualizado_em": "2026-10-10T12:00:00Z",
    }


def test_categorias_pela_divisao_do_cadastro_e_sem_cadastro(api_vendas):
    corpo = api_vendas.get(URL).json()

    assert [(c["categoria"], c["faturamento"], c["notas"]) for c in corpo["por_categoria"]] == [
        ("HIDRAULICA", "520.00", 2),
        ("TINTAS", "150.00", 2),
        ("SEM CATEGORIA", "80.00", 1),
    ]
    assert corpo["produtos"][0] == {
        "id_produto": "20",
        "id_subproduto": "20",
        "descricao": "CADASTRO 20",
        "quantidade": "11.0000",
        "faturamento": "520.00",
    }

    assert corpo["produtos"][-1]["descricao"] == "PRODUTO 99"


def test_periodo_com_comparacao_canal_e_empresa(api_vendas):
    corpo = api_vendas.get(
        URL,
        params={
            "data_inicial": "2026-10-01",
            "data_final": "2026-10-02",
            "comparar_inicial": "2026-09-01",
            "comparar_final": "2026-09-02",
            "canal": "balcao",
            "empresa": "1",
        },
    ).json()

    assert corpo["filtro"]["canal"] == "balcao"

    assert corpo["totais"]["devolucoes"] is None
    assert corpo["totais"]["faturamento_liquido"] == corpo["totais"]["faturamento"]
    assert corpo["formas_pagamento"] is None
    assert all(p["devolucoes"] is None for p in corpo["serie"])
    assert corpo["filtro"]["empresa"]["codigo"] == "1"
    assert (corpo["totais"]["faturamento"], corpo["totais"]["notas"]) == ("120.00", 1)
    assert (corpo["comparacao"]["faturamento"], corpo["comparacao"]["notas"]) == ("50.00", 1)
    assert corpo["granularidade"] == "dia"
    assert [(p["chave"], p["faturamento"]) for p in corpo["serie"]] == [
        ("2026-10-01", "120.00"),
        ("2026-10-02", "0"),
    ]
    assert [(e["empresa"]["codigo"], e["ticket_medio"]) for e in corpo["por_empresa"]] == [
        ("1", "120.00")
    ]


def test_categorias_alem_do_limite_viram_outras(vendas_db):
    empresa = vendas_db.query(Empresa).filter_by(codigo="2").one()
    notas = []
    for n in range(service.CATEGORIAS_NO_GRAFICO + 2):
        produto = f"5{n}"
        vendas_db.add(
            Produto(
                id_produto=produto,
                id_subproduto=produto,
                divisao=f"DIVISAO {n:02d}",
                sincronizado_em=AGORA,
            )
        )
        notas.append(_venda(f"9{n}", 8300, (produto, str(100 - n), "1")))
    vendas_db.flush()
    _gravar_dia(
        vendas_db,
        empresa.id,
        date(2026, 10, 5),
        notas,
        completo=True,
        execucao_id=None,
        momento=AGORA,
    )

    resumo = service.resumo_vendas(
        vendas_db,
        service.FiltroVendas(
            empresa=empresa,
            periodo=service.Intervalo(date(2026, 10, 5), date(2026, 10, 5)),
        ),
    )
    nomes = [f.chave for f in resumo.por_categoria]
    assert len(nomes) == service.CATEGORIAS_NO_GRAFICO
    assert nomes[-1] == "OUTRAS"
    assert sum(f.faturamento for f in resumo.por_categoria) == resumo.totais.faturamento


def test_formas_de_pagamento_todas_sem_outras(vendas_db):
    empresa = vendas_db.query(Empresa).filter_by(codigo="2").one()
    dia = date(2026, 10, 6)
    titulos: dict[tuple[str, str, str], Recebimento] = {}
    for n in range(12):
        titulos.update(
            _titulos((f"F{n:02d}", (n, f"FORMA {n:02d}"), str(100 - n), dia, str(100 - n), dia))
        )
    _gravar_dia(
        vendas_db,
        empresa.id,
        date(2026, 10, 6),
        [_venda("70", 8300, ("10", "10.00", "1"))],
        completo=True,
        execucao_id=None,
        momento=AGORA,
        titulos=titulos,
    )
    vendas_db.flush()

    resumo = service.resumo_vendas(
        vendas_db,
        service.FiltroVendas(
            empresa=empresa,
            periodo=service.Intervalo(date(2026, 10, 6), date(2026, 10, 6)),
        ),
    )
    assert [f.forma for f in resumo.formas_pagamento or []] == [f"FORMA {n:02d}" for n in range(12)]


def test_intervalo_pela_metade_422(api_vendas):
    resposta = api_vendas.get(URL, params={"data_inicial": "2026-10-01"})
    assert resposta.status_code == 422


def test_comparacao_sem_periodo_422(api_vendas):
    resposta = api_vendas.get(
        URL, params={"comparar_inicial": "2026-09-01", "comparar_final": "2026-09-02"}
    )
    assert resposta.status_code == 422


def test_empresa_desconhecida_404(api_vendas):
    assert api_vendas.get(URL, params={"empresa": "77"}).status_code == 404


def test_devolucoes_no_periodo_e_na_serie(api_vendas):
    corpo = api_vendas.get(
        URL, params={"data_inicial": "2026-10-01", "data_final": "2026-10-02", "empresa": "1"}
    ).json()

    assert (corpo["totais"]["devolucoes"], corpo["totais"]["faturamento_liquido"]) == (
        "30.00",
        "590.00",
    )
    assert [(p["chave"], p["devolucoes"]) for p in corpo["serie"]] == [
        ("2026-10-01", "30.00"),
        ("2026-10-02", "0"),
    ]
    assert [f["forma"] for f in corpo["formas_pagamento"]] == ["PIX TEF", "CARTAO DEBITO TEF"]


def test_ranking_de_vendedores_com_media(vendas_db, api_vendas):
    vendas_db.add(Vendedor(id_erp="8", nome="VENDEDORA FICTICIA", consultado_em=AGORA))
    vendas_db.flush()
    vendedores = api_vendas.get(URL).json()["vendedores"]

    assert vendedores["media_faturamento"] == "335.00"
    assert [
        (v["id_vendedor"], v["faturamento"], v["notas"], v["ticket_medio"], v["abaixo_da_media"])
        for v in vendedores["vendedores"]
    ] == [("8", "500.00", 1, "500.00", False), ("7", "170.00", 2, "85.00", True)]
    assert [e["codigo"] for e in vendedores["vendedores"][1]["empresas"]] == ["1"]

    assert [v["nome"] for v in vendedores["vendedores"]] == ["VENDEDORA FICTICIA", None]
    assert vendedores["vendedores"][0]["faturamento_comparacao"] is None
    assert (vendedores["sem_vendedor_faturamento"], vendedores["sem_vendedor_notas"]) == (
        "80.00",
        1,
    )


def test_vendedor_generico_do_erp_conta_como_sem_vendedor(vendas_db, api_vendas):

    vendas_db.add(Vendedor(id_erp="7", nome=" vendedor  exemplo ", consultado_em=AGORA))
    vendas_db.flush()
    vendedores = api_vendas.get(URL).json()["vendedores"]

    assert [v["id_vendedor"] for v in vendedores["vendedores"]] == ["8"]
    assert vendedores["media_faturamento"] == "500.00"
    assert (vendedores["sem_vendedor_faturamento"], vendedores["sem_vendedor_notas"]) == (
        "250.00",
        3,
    )


def test_vendedores_no_filtro_com_comparacao(api_vendas):
    vendedores = api_vendas.get(
        URL,
        params={
            "data_inicial": "2026-10-01",
            "data_final": "2026-10-02",
            "comparar_inicial": "2026-09-01",
            "comparar_final": "2026-09-02",
            "canal": "balcao",
        },
    ).json()["vendedores"]

    assert [
        (v["id_vendedor"], v["faturamento"], v["faturamento_comparacao"])
        for v in vendedores["vendedores"]
    ] == [("7", "120.00", "50.00")]
    assert vendedores["media_faturamento"] == "120.00"
    assert vendedores["vendedores"][0]["abaixo_da_media"] is False


def test_dias_escolhidos_somam_so_esses_dias(api_vendas):
    corpo = api_vendas.get(URL, params={"dias": "2026-10-02,2026-09-02", "empresa": "1"}).json()

    assert corpo["filtro"]["dias"] == ["2026-09-02", "2026-10-02"]
    assert (corpo["filtro"]["data_inicial"], corpo["filtro"]["data_final"]) == (
        "2026-09-02",
        "2026-10-02",
    )

    assert (corpo["totais"]["faturamento"], corpo["totais"]["notas"]) == ("50.00", 1)
    assert corpo["totais"]["devolucoes"] == "0"
    assert corpo["granularidade"] == "dia"
    assert [(p["chave"], p["faturamento"]) for p in corpo["serie"]] == [
        ("2026-09-02", "50.00"),
        ("2026-10-02", "0"),
    ]
    assert corpo["formas_pagamento"] == []


def test_canais_sem_venda_aparecem_zerados(api_vendas):

    corpo = api_vendas.get(URL, params={"dias": "2026-10-02,2026-09-02", "empresa": "1"}).json()

    canais = corpo["por_canal"]
    assert sorted(c["canal"] for c in canais) == ["balcao", "faturamento", "televendas"]
    assert (canais[0]["faturamento"], canais[0]["notas"]) == ("50.00", 1)
    assert all((c["faturamento"], c["notas"]) == ("0", 0) for c in canais[1:])


def test_com_filtro_de_canal_so_o_canal_filtrado(api_vendas):
    corpo = api_vendas.get(URL, params={"canal": "televendas", "empresa": "1"}).json()

    assert [c["canal"] for c in corpo["por_canal"]] == ["televendas"]


def test_dias_escolhidos_com_devolucao_e_recebimento(api_vendas):
    corpo = api_vendas.get(URL, params={"dias": "2026-10-01"}).json()

    assert corpo["totais"]["devolucoes"] == "30.00"
    assert [f["forma"] for f in corpo["formas_pagamento"]] == ["PIX TEF", "CARTAO DEBITO TEF"]
    assert [p["chave"] for p in corpo["serie"]] == ["2026-10-01"]


@pytest.mark.parametrize(
    "params",
    [
        {"dias": "2026-10-01", "data_inicial": "2026-10-01", "data_final": "2026-10-02"},
        {"dias": "2026-10-01", "comparar_inicial": "2026-09-01", "comparar_final": "2026-09-02"},
        {"dias": "01/10/2026"},
        {"dias": ""},
        {"dias": ",".join(f"2026-0{1 + n // 28}-{1 + n % 28:02d}" for n in range(61))},
    ],
)
def test_dias_invalidos_422(api_vendas, params):
    assert api_vendas.get(URL, params=params).status_code == 422


URL_EXCEL_DESCONTOS = "/api/v1/vendas/descontos/exportar"
D_DESCONTOS = date(2026, 10, 5)


def _venda_com_desconto(planilha, coi, valor, desconto, vendedor, cancelada=False):
    nota, itens = _venda(planilha, coi, ("10", valor, "1"), cancelada=cancelada, vendedor=vendedor)
    return nota, [replace(itens[0], valor_desconto=Decimal(desconto))]


@pytest.fixture
def com_descontos(vendas_db):
    db = vendas_db
    loja = db.scalar(select(Empresa).where(Empresa.codigo == "1"))
    db.add(Vendedor(id_erp="7", nome="  MARIA   SILVA ", consultado_em=AGORA))
    db.add(Vendedor(id_erp="2", nome="VENDEDOR EXEMPLO", consultado_em=AGORA))
    db.flush()
    _gravar_dia(
        db,
        loja.id,
        D_DESCONTOS,
        [
            _venda_com_desconto("A1", 8300, "90.00", "10.00", "7"),
            _venda_com_desconto("A2", 3001, "20.00", "30.00", "7"),
            _venda_com_desconto("A3", 8001, "50.00", "5.00", "555"),
            _venda_com_desconto("A4", 8300, "50.00", "4.00", "2"),
            _venda_com_desconto("A5", 8300, "50.00", "0", "7"),
            _venda_com_desconto("A6", 8300, "50.00", "9.00", "7", cancelada=True),
        ],
        completo=True,
        execucao_id=None,
        momento=AGORA,
    )
    db.flush()
    return db


def _planilha_descontos(api, **params):
    resposta = api.get(
        URL_EXCEL_DESCONTOS,
        params={"data_inicial": "2026-10-05", "data_final": "2026-10-05", **params},
    )
    assert resposta.status_code == 200
    assert 'filename="vendas_descontos_' in resposta.headers["content-disposition"]
    return load_workbook(BytesIO(resposta.content))


def test_exporta_descontos_uma_linha_por_nota_com_data_hora_e_vendedor(api_vendas, com_descontos):
    livro = _planilha_descontos(api_vendas)
    linhas = list(livro["Descontos"].iter_rows(values_only=True))

    assert linhas[1][0] == "Período: 05/10/2026 a 05/10/2026"
    cabecalho = linhas.index(
        (
            "Data",
            "Hora",
            "Vendedor",
            "Desconto (R$)",
            "Loja",
            "Nota",
            "Canal",
            "Valor da nota (R$)",
            "% de desconto",
        )
    )
    notas = linhas[cabecalho + 1 : -1]

    assert {n[5]: (n[2], n[3], n[7]) for n in notas} == {
        "A1": ("MARIA SILVA", 10.0, 90.0),
        "A2": ("MARIA SILVA", 30.0, 20.0),
        "A3": ("Vendedor 555", 5.0, 50.0),
        "A4": ("Sem vendedor", 4.0, 50.0),
    }
    hora = AGORA.astimezone(ZoneInfo(get_settings().tz)).time().replace(tzinfo=None)
    assert {(n[0].date(), n[1]) for n in notas} == {(D_DESCONTOS, hora)}
    assert linhas[-1][2:4] == ("Total", f"=SUM(D{cabecalho + 2}:D{cabecalho + 5})")


def test_descontos_marca_em_amarelo_desconto_maior_que_a_nota(api_vendas, com_descontos):
    aba = _planilha_descontos(api_vendas)["Descontos"]
    cores = {
        linha[5].value: linha[0].fill.fgColor.rgb
        for linha in aba.iter_rows(min_row=2)
        if linha[5].value in ("A1", "A2")
    }
    assert str(cores["A2"]).endswith("FFF2CC")
    assert not str(cores["A1"]).endswith("FFF2CC")


def test_descontos_total_por_vendedor_do_maior_para_o_menor(api_vendas, com_descontos):
    aba = _planilha_descontos(api_vendas)["Por vendedor"]
    linhas = list(aba.iter_rows(min_row=4, values_only=True))
    assert [linha[0] for linha in linhas] == [
        "MARIA SILVA",
        "Vendedor 555",
        "Sem vendedor",
        "Total",
    ]
    assert linhas[0][2].startswith("=SUMIF(Descontos!$C$")


def _notas_da_aba(aba):
    return [
        linha[5] for linha in aba.iter_rows(values_only=True) if linha[5] and linha[5] != "Nota"
    ]


def test_descontos_respeitam_empresa_e_canal(api_vendas, com_descontos):
    assert _notas_da_aba(_planilha_descontos(api_vendas, canal="televendas")["Descontos"]) == ["A3"]
    assert _notas_da_aba(_planilha_descontos(api_vendas, empresa="2")["Descontos"]) == []


def test_descontos_sem_nota_gera_planilha_zerada(api_vendas):
    livro = _planilha_descontos(api_vendas)
    assert list(livro["Descontos"].iter_rows(values_only=True))[-1][3] == 0
    assert list(livro["Por vendedor"].iter_rows(values_only=True))[-1][:3] == ("Total", 0, 0)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"data_inicial": "2026-10-05"},
        {"data_inicial": "2026-10-06", "data_final": "2026-10-05"},
    ],
)
def test_descontos_exigem_periodo_valido(api_vendas, params):
    assert api_vendas.get(URL_EXCEL_DESCONTOS, params=params).status_code == 422


def test_descontos_acima_do_limite_422(api_vendas, com_descontos, monkeypatch):
    monkeypatch.setattr("app.api.v1.vendas.LIMITE_EXPORTACAO", 2)
    resposta = api_vendas.get(
        URL_EXCEL_DESCONTOS, params={"data_inicial": "2026-10-05", "data_final": "2026-10-05"}
    )
    assert resposta.status_code == 422
    assert "período menor" in resposta.json()["detail"]


URL_EXCEL_FORMAS = "/api/v1/vendas/formas-pagamento/exportar"


def test_exporta_formas_de_pagamento_em_excel_com_grafico(api_vendas):
    resposta = api_vendas.get(
        URL_EXCEL_FORMAS, params={"data_inicial": "2026-10-01", "data_final": "2026-10-02"}
    )

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="vendas_formas_pagamento_' in resposta.headers["content-disposition"]
    aba = load_workbook(BytesIO(resposta.content))["Formas de pagamento"]
    linhas = list(aba.iter_rows(values_only=True))
    assert linhas[1][0] == "Período: 01/10/2026 a 02/10/2026"
    assert linhas[2][0] == "Empresa: todas (consolidado)"
    cabecalho = linhas.index(
        ("Forma de pagamento", "Valor recebido", "Quantidade (parcelas)", "Participação")
    )
    assert [linha[:3] for linha in linhas[cabecalho + 1 : cabecalho + 4]] == [
        ("Pix tef", 480.0, 4),
        ("Cartao debito tef", 220.0, 2),
        ("Total", "=SUM(B7:B8)", "=SUM(C7:C8)"),
    ]
    assert len(aba._charts) == 1


def test_exportar_formas_com_canal_422(api_vendas):
    assert api_vendas.get(URL_EXCEL_FORMAS, params={"canal": "balcao"}).status_code == 422
