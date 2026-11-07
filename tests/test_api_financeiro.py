import pytest
from fastapi.testclient import TestClient

from tests.conftest import app_com_sessao, token_para
from tests.test_api_vendas import vendas_db  # noqa: F401 (fixture)

pytestmark = pytest.mark.integration

URL = "/api/v1/financeiro/resumo"


@pytest.fixture
def api_financeiro(vendas_db, criar_usuario_teste):  # noqa: F811
    operador = criar_usuario_teste("op.financeiro", "OPERADOR", modulos=["FINANCEIRO"])
    app = app_com_sessao(vendas_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_sem_token_401(client):
    assert client.get(URL).status_code == 401


def test_so_com_vendas_403(db_vazio, criar_usuario_teste):
    operador = criar_usuario_teste("op.so.vendas", "OPERADOR", modulos=["VENDAS"])
    app = app_com_sessao(db_vazio)
    assert TestClient(app, headers=token_para(app, operador)).get(URL).status_code == 403


def test_sem_periodo_vendido_pago_e_pendente(api_financeiro):
    corpo = api_financeiro.get(URL).json()

    assert corpo["filtro"] == {"empresa": None, "data_inicial": None, "data_final": None}
    vendas = corpo["vendas"]
    assert (
        vendas["valor"],
        vendas["valor_pago"],
        vendas["valor_pendente"],
        vendas["parcelas"],
    ) == (
        "750.00",
        "640.00",
        "110.00",
        7,
    )
    assert vendas["formas"] == [
        {
            "forma": "PIX TEF",
            "valor": "480.00",
            "valor_pago": "480.00",
            "valor_pendente": "0.00",
            "parcelas": 4,
        },
        {
            "forma": "CARTAO DEBITO TEF",
            "valor": "220.00",
            "valor_pago": "110.00",
            "valor_pendente": "110.00",
            "parcelas": 2,
        },
        {
            "forma": "BOLETO BANCO",
            "valor": "50.00",
            "valor_pago": "50.00",
            "valor_pendente": "0.00",
            "parcelas": 1,
        },
    ]

    assert (corpo["recebidos"]["total"], corpo["recebidos"]["de_vendas_anteriores"]) == (
        "640.00",
        "0",
    )

    rec = corpo["recebidos"]
    assert (rec["de_boletos"], rec["das_vendas_do_periodo"], rec["outros_anteriores"]) == (
        "50.00",
        "590.00",
        "0",
    )
    assert corpo["cobertura"]["ate"] == "2026-10-02"


def test_recebidos_no_periodo_com_o_boleto_de_venda_anterior(api_financeiro):
    corpo = api_financeiro.get(
        URL, params={"data_inicial": "2026-10-01", "data_final": "2026-10-02", "empresa": "1"}
    ).json()

    assert corpo["filtro"]["empresa"]["codigo"] == "1"

    assert corpo["recebidos"] == {
        "total": "560.00",
        "de_vendas_anteriores": "50.00",
        "de_boletos": "50.00",
        "das_vendas_do_periodo": "510.00",
        "outros_anteriores": "0",
        "juros": "2.50",
        "titulos": 5,
        "formas": [
            {"forma": "PIX TEF", "valor": "400.00", "titulos": 3},
            {"forma": "CARTAO DEBITO TEF", "valor": "110.00", "titulos": 1},
            {"forma": "BOLETO BANCO", "valor": "50.00", "titulos": 1},
        ],
    }

    assert [f["forma"] for f in corpo["vendas"]["formas"]] == ["PIX TEF", "CARTAO DEBITO TEF"]
    assert corpo["vendas"]["valor_pendente"] == "110.00"


def test_dia_sem_venda_so_com_o_boleto_recebido(api_financeiro):
    corpo = api_financeiro.get(
        URL, params={"data_inicial": "2026-10-02", "data_final": "2026-10-02", "empresa": "1"}
    ).json()

    assert corpo["vendas"]["formas"] == []
    assert corpo["vendas"]["valor"] == "0"
    assert [(f["forma"], f["valor"]) for f in corpo["recebidos"]["formas"]] == [
        ("BOLETO BANCO", "50.00")
    ]
    assert corpo["recebidos"]["de_vendas_anteriores"] == "50.00"
    assert corpo["recebidos"]["de_boletos"] == "50.00"
    assert corpo["recebidos"]["das_vendas_do_periodo"] == "0.00"


@pytest.mark.parametrize(
    ("params", "codigo"),
    [({"data_inicial": "2026-10-01"}, 422), ({"empresa": "99"}, 404)],
)
def test_parametros_invalidos(api_financeiro, params, codigo):
    assert api_financeiro.get(URL, params=params).status_code == codigo


PARCELAS = "/api/v1/financeiro/parcelas"


def test_parcelas_pendentes_pelo_lancamento(api_financeiro):
    corpo = api_financeiro.get(
        PARCELAS,
        params={"data_inicial": "2026-10-01", "data_final": "2026-10-02", "situacao": "pendentes"},
    ).json()

    assert (corpo["total"], corpo["valor_pendente"], corpo["total_paginas"]) == (1, "110.00", 1)
    [parcela] = corpo["itens"]
    assert parcela == {
        "empresa": "1",
        "empresa_nome": "Loja 1",
        "documento": "T5",
        "titulo": "1",
        "parcela": "1",
        "forma": "CARTAO DEBITO TEF",
        "dia_lancamento": "2026-10-01",
        "vencimento": parcela["vencimento"],
        "dia_pagamento": None,
        "valor": "110.00",
        "valor_pago": "0.00",
        "valor_pendente": "110.00",
        "juros": "0.00",
        "desconto": parcela["desconto"],
        "situacao": "PENDENTE",
    }


def test_parcelas_pelo_pagamento_batem_com_o_recebido(api_financeiro):
    params = {"data_inicial": "2026-10-01", "data_final": "2026-10-02", "empresa": "1"}
    recebido = api_financeiro.get(URL, params=params).json()["recebidos"]
    corpo = api_financeiro.get(PARCELAS, params={**params, "data_por": "pagamento"}).json()

    assert corpo["total"] == recebido["titulos"] == 5
    assert corpo["valor_pago"] == recebido["total"] == "560.00"

    assert [(p["documento"], p["situacao"]) for p in corpo["itens"]][0] == ("B1", "PAGA")


def test_parcelas_por_forma_e_paginas(api_financeiro):
    corpo = api_financeiro.get(
        PARCELAS, params={"forma": "PIX TEF", "tamanho_pagina": 2, "pagina": 2}
    ).json()

    assert (corpo["total"], corpo["total_paginas"], corpo["valor"]) == (4, 2, "480.00")
    assert len(corpo["itens"]) == 2
    assert {p["forma"] for p in corpo["itens"]} == {"PIX TEF"}


def test_parcelas_sem_modulo_403(db_vazio, criar_usuario_teste):
    operador = criar_usuario_teste("op.parcelas.vendas", "OPERADOR", modulos=["VENDAS"])
    app = app_com_sessao(db_vazio)
    assert TestClient(app, headers=token_para(app, operador)).get(PARCELAS).status_code == 403


@pytest.mark.parametrize(
    "params",
    [{"data_por": "vencimento"}, {"situacao": "abertas"}, {"tamanho_pagina": 500}],
)
def test_parcelas_parametros_invalidos(api_financeiro, params):
    assert api_financeiro.get(PARCELAS, params=params).status_code == 422
