import pytest
from pydantic import ValidationError

from app.erp.errors import ErpApiRespostaInvalidaError
from app.erp.schemas import (
    Clausula,
    Operador,
    OperadorLogico,
    RequisicaoPaginada,
    TokenResposta,
    interpretar_pagina,
)


def test_clausula_gera_o_formato_do_manual():
    c = Clausula(campo="campoTeste", operador=Operador.IGUAL, valor="1")

    assert c.to_payload() == {
        "campo": "campoTeste",
        "valor": "1",
        "operadorLogico": "AND",
        "operador": "IGUAL",
    }


def test_operadores_sao_exatamente_os_do_manual():
    assert {o.value for o in Operador} == {
        "IGUAL",
        "IGUAL_NULL",
        "EQUAL",
        "MENOR",
        "MAIOR",
        "LIKE",
        "MENOR_IGUAL",
        "MAIOR_IGUAL",
    }

    assert {o.value for o in OperadorLogico} == {"AND"}


def test_clausula_exige_campo_e_operador_valido():
    with pytest.raises(ValidationError):
        Clausula(campo="", operador=Operador.IGUAL)
    with pytest.raises(ValidationError):
        Clausula(campo="x", operador="DIFERENTE")


def test_requisicao_paginada_padrao_e_pagina_1_sem_clausulas():
    assert RequisicaoPaginada().to_payload() == {"page": 1, "clausulas": []}


def test_requisicao_paginada_com_clausulas_e_proxima():
    r = RequisicaoPaginada(
        pagina=2,
        clausulas=(
            Clausula(campo="a", operador=Operador.MAIOR_IGUAL, valor="10"),
            Clausula(campo="a", operador=Operador.MENOR_IGUAL, valor="20"),
        ),
    )

    payload = r.proxima().to_payload()

    assert payload["page"] == 3
    assert [c["operador"] for c in payload["clausulas"]] == ["MAIOR_IGUAL", "MENOR_IGUAL"]
    assert r.pagina == 2


def test_pagina_zero_e_recusada():
    with pytest.raises(ValidationError):
        RequisicaoPaginada(pagina=0)


def test_token_resposta_esconde_o_token_e_ignora_extras():
    t = TokenResposta.model_validate(
        {"access_token": "tok-abc", "expires_in": 86400, "scope": "x", "refresh_token": "r"}
    )

    assert t.access_token.get_secret_value() == "tok-abc"
    assert t.expires_in == 86400
    assert "tok-abc" not in repr(t)


def test_token_resposta_sem_expires_in_e_aceita():
    assert TokenResposta.model_validate({"access_token": "x"}).expires_in is None


@pytest.mark.parametrize(
    "has_next,esperado", [(True, True), (False, False), ("True", True), ("false", False)]
)
def test_interpretar_pagina_aceita_has_next_booleano_ou_texto(has_next, esperado):
    p = interpretar_pagina(
        {"lista": [{"id": 1}], "hasNext": has_next, "Total": "150"},
        pagina=1,
        campo_registros="lista",
    )

    assert p.tem_proxima is esperado
    assert p.total == 150
    assert p.registros == [{"id": 1}]


def test_interpretar_pagina_total_e_opcional():
    p = interpretar_pagina({"lista": [], "hasNext": False}, pagina=1, campo_registros="lista")
    assert p.total is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"hasNext": False},
        {"lista": "x", "hasNext": False},
        {"lista": [1, 2], "hasNext": False},
        {"lista": []},
        {"lista": [], "hasNext": "talvez"},
        {"lista": [], "hasNext": False, "Total": "muitos"},
        {"lista": [], "hasNext": False, "Total": True},
    ],
)
def test_interpretar_pagina_falha_alto_com_formato_inesperado(payload):
    with pytest.raises(ErpApiRespostaInvalidaError):
        interpretar_pagina(payload, pagina=1, campo_registros="lista")


def test_nomes_de_campos_da_resposta_sao_configuraveis():
    p = interpretar_pagina(
        {"itens": [{"a": 1}], "temMais": True, "qtd": 7},
        pagina=4,
        campo_registros="itens",
        campo_total="qtd",
        campo_tem_proxima="temMais",
    )

    assert (p.pagina, p.total, p.tem_proxima) == (4, 7, True)
