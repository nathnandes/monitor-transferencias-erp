import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.erp.config import ErpApiSettings
from app.erp.errors import ErpApiRespostaInvalidaError
from app.erp.servicos import (
    ROTA_SALDO_ESTOQUE_EMPRESA,
    RegistroInvalidoError,
    mapear_loja,
    mapear_saldo,
)
from tests.sync_fakes import ErpApiSimulado, loja, saldo, servicos_para


def test_mapeia_loja_com_nome_fantasia_e_bairro():
    resultado = mapear_loja(loja("3", "Loja Ficticia Tres", "Centro"))

    assert (resultado.id_erp, resultado.nome, resultado.bairro) == (
        "3",
        "Loja Ficticia Tres",
        "Centro",
    )


def test_loja_aceita_campos_em_maiusculas_e_nome_alternativo():
    resultado = mapear_loja({"IDEMPRESA": 7.0, "RazaoSocial": "  Razao Ficticia  "})

    assert resultado.id_erp == "7"
    assert resultado.nome == "Razao Ficticia"
    assert resultado.bairro is None


def test_loja_sem_idempresa_e_invalida_e_lista_so_nomes_de_campo():
    with pytest.raises(RegistroInvalidoError) as erro:
        mapear_loja({"nomefantasia": "valor-que-nao-pode-vazar"})

    assert "idempresa" in str(erro.value)
    assert "nomefantasia" in str(erro.value)
    assert "valor-que-nao-pode-vazar" not in str(erro.value)


def test_mapeia_saldo_documentado():
    resultado = mapear_saldo(saldo("1", "100", "12.5", "10.25", reservado="2.25", lote="L-01"))

    assert resultado.id_empresa == "1"
    assert resultado.chave == ("100", "1", "1", "L-01")
    assert resultado.saldo_atual == Decimal("12.5")
    assert resultado.saldo_reservado == Decimal("2.25")
    assert resultado.saldo_disponivel == Decimal("10.25")
    assert resultado.utiliza_lote is True
    assert resultado.permite_estoque_negativo is False

    assert resultado.data_alteracao == datetime(2026, 10, 1, 12, 30, tzinfo=UTC)
    assert resultado.inativo_erp is False


def test_disponivel_vem_da_api_e_nao_e_recalculado():

    resultado = mapear_saldo(saldo("1", "100", "10", "5", reservado="2"))

    assert resultado.saldo_disponivel == Decimal("5")


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [(10, "10"), (1.5, "1.5"), ("3,75", "3.75"), ("-2.000", "-2.000"), (None, None), ("", None)],
)
def test_converte_quantidades(bruto, esperado):
    resultado = mapear_saldo(saldo("1", "100", bruto, "0"))

    assert resultado.saldo_atual == (Decimal(esperado) if esperado else None)


def test_sem_lote_vira_texto_vazio_para_a_chave_unica():
    assert mapear_saldo(saldo("1", "100", "1", "1")).descricao_lote == ""


def test_reserva_e_opcional():
    registro = saldo("1", "100", "1", "1")
    del registro["qtdsaldoreserva"]

    assert mapear_saldo(registro).saldo_reservado is None


@pytest.mark.parametrize("campo", ["idproduto", "idsubproduto", "idlocalestoque", "qtdsaldoatual"])
def test_campo_obrigatorio_ausente_e_invalido(campo):
    registro = saldo("1", "100", "1", "1")
    del registro[campo]

    with pytest.raises(RegistroInvalidoError, match=campo):
        mapear_saldo(registro)


def test_quantidade_nao_numerica_e_invalida():
    with pytest.raises(RegistroInvalidoError, match="qtdsaldoatual"):
        mapear_saldo(saldo("1", "100", "muito", "1"))


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("01/10/2026 08:30:00", datetime(2026, 10, 1, 12, 30, tzinfo=UTC)),
        ("2026-10-01 08:30:00", datetime(2026, 10, 1, 12, 30, tzinfo=UTC)),
        ("2026-10-01T08:30:00-03:00", datetime(2026, 10, 1, 11, 30, tzinfo=UTC)),
        (1790000000000, datetime.fromtimestamp(1790000000, UTC)),
        ("formato-desconhecido", None),
    ],
)
def test_datas(bruto, esperado):
    assert mapear_saldo(saldo("1", "100", "1", "1", dtalteracao=bruto)).data_alteracao == esperado


def test_pagina_de_saldo_envia_filtro_por_empresa_na_rota_validada():
    simulado = ErpApiSimulado().com_estoque("2", [saldo("2", "100", "1", "1")])
    servicos = servicos_para(simulado)

    pagina = servicos.pagina_saldo_estoque("2", 1)

    assert len(pagina.registros) == 1
    servico = [r for r in simulado.requisicoes if r.url.path == ROTA_SALDO_ESTOQUE_EMPRESA][0]
    assert servico.method == "POST"
    assert servico.headers["Content-Type"] == "application/json"
    assert servico.headers["Authorization"] == "Bearer token-ficticio-sync-0001"
    assert json.loads(servico.content) == {
        "page": 1,
        "clausulas": [
            {"campo": "idempresa", "valor": "2", "operadorLogico": "AND", "operador": "IGUAL"}
        ],
    }


def test_campo_de_registros_errado_lista_as_chaves_recebidas():
    simulado = ErpApiSimulado().com_estoque("1", [saldo("1", "100", "1", "1")])
    servicos = servicos_para(simulado, campo_registros="content")

    with pytest.raises(ErpApiRespostaInvalidaError) as erro:
        servicos.pagina_saldo_estoque("1", 1)

    assert "'content' ausente" in str(erro.value)
    assert "['data', 'hasNext', 'total']" in str(erro.value)
    assert erro.value.rota == ROTA_SALDO_ESTOQUE_EMPRESA


def test_aceita_nomes_erp_para_conexao_e_credenciais(monkeypatch):
    monkeypatch.setenv("ERP_BASE_URL", "https://erp.teste.invalid:7000")
    monkeypatch.setenv("ERP_USERNAME", "usuario-erp")
    monkeypatch.setenv("ERP_PASSWORD", "senha-erp-ficticia")
    monkeypatch.setenv("ERP_CLIENT_ID", "cliente-erp")
    monkeypatch.setenv("ERP_CLIENT_SECRET", "segredo-erp-ficticio")

    s = ErpApiSettings(_env_file=None)

    assert s.base_url == "https://erp.teste.invalid:7000"
    assert s.username == "usuario-erp"
    assert s.password.get_secret_value() == "senha-erp-ficticia"
    assert s.client_id == "cliente-erp"
    assert s.client_secret.get_secret_value() == "segredo-erp-ficticio"
    assert "senha-erp-ficticia" not in repr(s)
    assert "segredo-erp-ficticio" not in repr(s)


def test_nome_erpapi_tem_precedencia_sobre_erp(monkeypatch):
    monkeypatch.setenv("ERP_BASE_URL", "https://erp.teste.invalid")
    monkeypatch.setenv("ERPAPI_BASE_URL", "https://erpapi.teste.invalid")

    assert ErpApiSettings(_env_file=None).base_url == "https://erpapi.teste.invalid"


def test_erpapi_vazio_nao_esconde_erp_preenchido(monkeypatch):
    monkeypatch.setenv("ERPAPI_BASE_URL", "")
    monkeypatch.setenv("ERP_BASE_URL", "https://erp.teste.invalid")

    assert ErpApiSettings(_env_file=None).base_url == "https://erp.teste.invalid"


def test_filtros_validados_no_ambiente():
    from zoneinfo import ZoneInfo

    servicos = servicos_para(ErpApiSimulado())
    servicos.fuso = ZoneInfo("America/Porto_Velho")

    (data,) = servicos.filtro_alterado_desde(datetime(2026, 10, 7, 17, 0, tzinfo=UTC))
    assert data.to_payload() == {
        "campo": "dtalteracao",
        "valor": "2026-10-07 13:00:00",
        "operadorLogico": "AND",
        "operador": "MAIOR_IGUAL",
    }
    (reserva,) = servicos.filtro_com_reserva()
    assert (reserva.campo, reserva.operador.value, reserva.valor) == (
        "qtdsaldoreserva",
        "MAIOR",
        "0",
    )
    produto = servicos.filtro_produto("10", "11")
    assert [(c.campo, c.valor) for c in produto] == [("idproduto", "10"), ("idsubproduto", "11")]


def test_fuso_invalido_e_recusado():
    with pytest.raises(ValueError, match="fuso desconhecido"):
        ErpApiSettings(_env_file=None, fuso="America/Nao_Existe")


def test_mapeia_preco_com_numeros_json_e_datas_ausentes():
    from app.erp.servicos import mapear_preco
    from tests.sync_fakes import preco

    resultado = mapear_preco(
        preco(
            "1",
            "9798",
            varejo=12.9,
            custo=0.1,
            dtinipromocaovar="2026-10-01 00:00:00",
            dtfimpromocaovar="2026-10-31 00:00:00",
            valpromvarejo=11.5,
        )
    )

    assert (resultado.id_empresa, resultado.id_produto, resultado.id_subproduto) == (
        "1",
        "9798",
        "1",
    )

    assert resultado.custo_gerencial == Decimal("0.1")
    assert resultado.preco_varejo == Decimal("12.9")
    assert resultado.preco_promocao_varejo == Decimal("11.5")

    assert resultado.inicio_promocao_varejo == datetime(2026, 10, 1, 4, 0, tzinfo=UTC)
    assert resultado.inicio_promocao_atacado is None
    assert resultado.inativo_erp is False


def test_preco_sem_chave_e_recusado():
    from app.erp.servicos import mapear_preco

    with pytest.raises(RegistroInvalidoError, match="idsubproduto"):
        mapear_preco({"idempresa": 1, "idproduto": 2, "valprecovarejo": 1.0})


def test_mapeia_produto():
    from app.erp.servicos import mapear_produto
    from tests.sync_fakes import produto

    resultado = mapear_produto(
        produto(
            "9798", "CAFE FICTICIO 500G", descricao="MARCA FICTICIA", nrcodbarprod=7891234567890
        )
    )

    assert resultado.chave == ("9798", "9798")
    assert resultado.descricao == "CAFE FICTICIO 500G"
    assert resultado.marca == "MARCA FICTICIA"
    assert resultado.codigo_barras == "7891234567890"
    assert resultado.bloqueado_venda is False


def test_produtos_sao_consultados_sem_filtro_de_empresa():
    from app.erp.servicos import ROTA_CAD_PRODUTOS
    from tests.sync_fakes import produto

    simulado = ErpApiSimulado().com_produtos([produto("9798")])
    servicos = servicos_para(simulado)

    resposta = servicos.pagina_produtos(1)

    assert len(resposta.registros) == 1
    corpo = json.loads(simulado.requisicoes[-1].content)
    assert simulado.requisicoes[-1].url.path == ROTA_CAD_PRODUTOS
    assert corpo == {"page": 1, "clausulas": []}
