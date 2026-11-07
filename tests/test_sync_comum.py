import pytest

from app.erp.errors import (
    ErpApiAcessoNegadoError,
    ErpApiConexaoError,
    ErpApiDesabilitadoError,
    ErpApiErroServidorError,
    ErpApiLimiteRequisicoesError,
    ErpApiNaoAutorizadoError,
    ErpApiNaoEncontradoError,
    ErpApiPaginacaoExcedidaError,
    ErpApiRequisicaoInvalidaError,
    ErpApiTimeoutError,
)
from app.erp.schemas import RespostaPaginada
from app.sync.comum import com_retry, eh_falha_geral, percorrer_paginas
from tests.sync_fakes import politica


class Roteiro:
    def __init__(self, *excecoes, valor="ok"):
        self.excecoes = list(excecoes)
        self.valor = valor
        self.chamadas = 0

    def __call__(self):
        self.chamadas += 1
        if self.excecoes:
            raise self.excecoes.pop(0)
        return self.valor


def test_falha_transitoria_e_repetida_com_espera_exponencial():
    regra, dormir = politica(tentativas=3)
    falhas = []
    chamada = Roteiro(ErpApiTimeoutError("t"), ErpApiErroServidorError("5xx", status_code=502))

    assert com_retry(chamada, regra, lambda e, t: falhas.append((type(e).__name__, t))) == "ok"
    assert chamada.chamadas == 3
    assert dormir.esperas == [2.0, 4.0]
    assert falhas == [("ErpApiTimeoutError", 1), ("ErpApiErroServidorError", 2)]


def test_desiste_depois_da_ultima_tentativa():
    regra, dormir = politica(tentativas=2)
    chamada = Roteiro(*[ErpApiConexaoError("c") for _ in range(3)])

    with pytest.raises(ErpApiConexaoError):
        com_retry(chamada, regra, lambda e, t: None)
    assert chamada.chamadas == 2
    assert dormir.esperas == [2.0]


@pytest.mark.parametrize(
    "excecao",
    [
        ErpApiRequisicaoInvalidaError("400", status_code=400),
        ErpApiNaoAutorizadoError("401", status_code=401),
        ErpApiAcessoNegadoError("403", status_code=403),
        ErpApiNaoEncontradoError("404", status_code=404),
    ],
)
def test_erro_nao_transitorio_nao_e_repetido(excecao):
    regra, dormir = politica()
    chamada = Roteiro(excecao)

    with pytest.raises(type(excecao)):
        com_retry(chamada, regra, lambda e, t: None)
    assert chamada.chamadas == 1
    assert dormir.esperas == []


def test_429_respeita_retry_after():
    regra, dormir = politica()
    chamada = Roteiro(ErpApiLimiteRequisicoesError("429", status_code=429, retry_after=7.0))

    com_retry(chamada, regra, lambda e, t: None)

    assert dormir.esperas == [7.0]


@pytest.mark.parametrize(
    ("excecao", "geral"),
    [
        (ErpApiDesabilitadoError("off"), True),
        (ErpApiNaoAutorizadoError("401"), True),
        (ErpApiTimeoutError("t"), True),
        (ErpApiConexaoError("c"), True),
        (ErpApiAcessoNegadoError("403"), False),
        (ErpApiNaoEncontradoError("404"), False),
        (ErpApiErroServidorError("500"), False),
        (ErpApiRequisicaoInvalidaError("400"), False),
    ],
)
def test_classificacao_de_falha_geral(excecao, geral):
    assert eh_falha_geral(excecao) is geral


def _pagina(numero, registros, tem_proxima):
    return RespostaPaginada(pagina=numero, registros=registros, total=None, tem_proxima=tem_proxima)


def test_percorre_todas_as_paginas_ate_has_next_falso():
    paginas = {1: [{"a": 1}] * 100, 2: [{"a": 2}] * 100, 3: [{"a": 3}] * 5}
    lidas = []

    def buscar(n):
        lidas.append(n)
        return _pagina(n, paginas[n], n < 3)

    leitura = percorrer_paginas(
        buscar, max_paginas=10, politica=politica()[0], ao_falhar=lambda *a: None
    )

    assert lidas == [1, 2, 3]
    assert leitura.paginas == 3
    assert len(leitura.registros) == 205


def test_retry_por_pagina_informa_a_pagina_que_falhou():
    falhas = []
    tentativas = {2: [ErpApiErroServidorError("503", status_code=503)]}

    def buscar(n):
        if tentativas.get(n):
            raise tentativas[n].pop(0)
        return _pagina(n, [{"n": n}], n < 2)

    leitura = percorrer_paginas(
        buscar,
        max_paginas=10,
        politica=politica()[0],
        ao_falhar=lambda e, t, p: falhas.append((p, t)),
    )

    assert leitura.paginas == 2
    assert falhas == [(2, 1)]


def test_teto_de_paginas_levanta_em_vez_de_terminar_calado():
    with pytest.raises(ErpApiPaginacaoExcedidaError):
        percorrer_paginas(
            lambda n: _pagina(n, [{"n": n}], True),
            max_paginas=3,
            politica=politica()[0],
            ao_falhar=lambda *a: None,
        )
