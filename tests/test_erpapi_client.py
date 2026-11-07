import logging

import httpx2
import pytest

from app.erp.client import ErpApiClient
from app.erp.errors import (
    ErpApiAcessoNegadoError,
    ErpApiConexaoError,
    ErpApiConfiguracaoError,
    ErpApiDesabilitadoError,
    ErpApiErroServidorError,
    ErpApiHttpError,
    ErpApiLimiteRequisicoesError,
    ErpApiNaoAutorizadoError,
    ErpApiNaoEncontradoError,
    ErpApiPaginacaoExcedidaError,
    ErpApiRequisicaoInvalidaError,
    ErpApiRespostaInvalidaError,
    ErpApiRotaNaoPermitidaError,
    ErpApiTimeoutError,
)
from app.erp.schemas import Clausula, Operador, RequisicaoPaginada
from tests.erpapi_fakes import (
    CLIENT_ID,
    CLIENT_SECRET,
    ROTA,
    SENHA,
    TOKEN_PATH,
    USUARIO,
    Relogio,
    ServidorFalso,
    corpo_json,
    criar_settings,
    form,
    resposta_pagina,
    resposta_token,
)

TOKEN_1 = "token-simulado-primeiro"
TOKEN_2 = "token-simulado-segundo"
REQ = RequisicaoPaginada()


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    def _proibido(*_a, **_k):
        raise AssertionError("tentativa de acesso a rede real nos testes")

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", _proibido)


@pytest.fixture
def servidor() -> ServidorFalso:
    return ServidorFalso()


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
def novo_client(servidor, relogio):
    criados: list[ErpApiClient] = []

    def _criar(**sobrescrever) -> ErpApiClient:
        c = ErpApiClient(
            criar_settings(**sobrescrever), transport=servidor.transport(), relogio=relogio
        )
        criados.append(c)
        return c

    yield _criar
    for c in criados:
        c.close()


def test_desabilitado_nao_faz_nenhuma_chamada(novo_client, servidor):
    client = novo_client(enabled=False)

    with pytest.raises(ErpApiDesabilitadoError):
        client.consultar(ROTA, REQ)
    with pytest.raises(ErpApiDesabilitadoError):
        client.autenticar()
    assert servidor.requisicoes == []


def test_configuracao_incompleta_lista_variaveis_sem_valores(novo_client, servidor):
    client = novo_client(client_id="", client_secret="")

    with pytest.raises(ErpApiConfiguracaoError) as exc:
        client.consultar(ROTA, REQ)

    assert "ERPAPI_CLIENT_ID" in str(exc.value)
    assert "ERPAPI_CLIENT_SECRET" in str(exc.value)
    assert SENHA not in str(exc.value)
    assert servidor.requisicoes == []


@pytest.mark.parametrize(
    "sobrescrever",
    [{"base_url": "erpapi.teste.invalid"}, {"token_path": "teste/token"}],
)
def test_url_ou_caminho_de_token_malformados(novo_client, servidor, sobrescrever):
    with pytest.raises(ErpApiConfiguracaoError):
        novo_client(**sobrescrever).consultar(ROTA, REQ)
    assert servidor.requisicoes == []


@pytest.mark.parametrize(
    "rota",
    [
        "/teste/outro-servico",
        "teste/servico-leitura",
        "//outro.host/x",
        "https://outro.host.invalid/teste/servico-leitura",
        "/teste/../servico-leitura",
        "/teste/servico-leitura?x=1",
        TOKEN_PATH,
    ],
)
def test_rota_fora_da_lista_branca_ou_malformada_e_recusada(novo_client, servidor, rota):
    client = novo_client(allowed_routes=f"{ROTA},{TOKEN_PATH}")

    with pytest.raises(ErpApiRotaNaoPermitidaError):
        client.consultar(rota, REQ)
    assert servidor.requisicoes == []


def test_lista_branca_vazia_bloqueia_tudo(novo_client, servidor):
    with pytest.raises(ErpApiRotaNaoPermitidaError):
        novo_client(allowed_routes="").consultar(ROTA, REQ)
    assert servidor.requisicoes == []


def test_pedido_de_token_segue_o_manual(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))

    novo_client().autenticar()

    (req,) = servidor.requisicoes
    assert req.method == "POST"
    assert str(req.url) == f"https://erpapi.teste.invalid{TOKEN_PATH}"
    assert req.headers["content-type"] == "application/x-www-form-urlencoded"
    assert "authorization" not in req.headers
    assert form(req) == {
        "client_id": CLIENT_ID,
        "grant_type": "password",
        "client_secret": CLIENT_SECRET,
        "username": USUARIO,
        "password": SENHA,
    }


def test_consulta_envia_json_e_bearer(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, resposta_pagina([{"id": 1}], has_next=False))
    req = RequisicaoPaginada(
        pagina=1, clausulas=(Clausula(campo="campoTeste", operador=Operador.IGUAL, valor="1"),)
    )

    resultado = novo_client().consultar(ROTA, req)

    (chamada,) = servidor.chamadas(ROTA)
    assert chamada.method == "POST"
    assert chamada.headers["content-type"] == "application/json"
    assert chamada.headers["authorization"] == f"Bearer {TOKEN_1}"
    assert corpo_json(chamada) == {
        "page": 1,
        "clausulas": [
            {"campo": "campoTeste", "valor": "1", "operadorLogico": "AND", "operador": "IGUAL"}
        ],
    }
    assert resultado["registros_teste"] == [{"id": 1}]


def test_token_e_reutilizado_enquanto_valido(novo_client, servidor, relogio):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1, expires_in=3600))
    servidor.enfileirar(ROTA, *[resposta_pagina([], has_next=False)] * 3)
    client = novo_client()

    for _ in range(3):
        client.consultar(ROTA, REQ)
        relogio.avancar(1000)

    assert len(servidor.chamadas(TOKEN_PATH)) == 1


def test_token_e_renovado_ao_entrar_na_margem(novo_client, servidor, relogio):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1, 3600), resposta_token(TOKEN_2, 3600))
    servidor.enfileirar(ROTA, resposta_pagina([], False), resposta_pagina([], False))
    client = novo_client(token_renew_margin_seconds=60)

    client.consultar(ROTA, REQ)
    relogio.avancar(3600 - 60)
    client.consultar(ROTA, REQ)

    assert len(servidor.chamadas(TOKEN_PATH)) == 2
    assert servidor.chamadas(ROTA)[1].headers["authorization"] == f"Bearer {TOKEN_2}"


def test_sem_expires_in_usa_validade_de_fallback(novo_client, servidor, relogio):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1, None), resposta_token(TOKEN_2, None))
    servidor.enfileirar(ROTA, *[resposta_pagina([], False)] * 3)
    client = novo_client(token_ttl_fallback_seconds=600, token_renew_margin_seconds=60)

    client.consultar(ROTA, REQ)
    relogio.avancar(500)
    client.consultar(ROTA, REQ)
    assert len(servidor.chamadas(TOKEN_PATH)) == 1
    relogio.avancar(100)
    client.consultar(ROTA, REQ)
    assert len(servidor.chamadas(TOKEN_PATH)) == 2


def test_token_de_12h_e_trocado_sozinho_quando_vence(novo_client, servidor, relogio):
    doze_horas = 12 * 3600
    servidor.enfileirar(
        TOKEN_PATH,
        resposta_token(TOKEN_1, expires_in=doze_horas),
        resposta_token(TOKEN_1, expires_in=300),
        resposta_token(TOKEN_2, expires_in=doze_horas),
    )
    servidor.enfileirar(ROTA, *[resposta_pagina([], False)] * 4)
    client = novo_client(token_renew_margin_seconds=300)

    client.consultar(ROTA, REQ)
    relogio.avancar(doze_horas - 600)
    client.consultar(ROTA, REQ)
    assert len(servidor.chamadas(TOKEN_PATH)) == 1

    relogio.avancar(300)
    client.consultar(ROTA, REQ)
    relogio.avancar(300)
    client.consultar(ROTA, REQ)

    assert len(servidor.chamadas(TOKEN_PATH)) == 3
    assert servidor.chamadas(ROTA)[-1].headers["authorization"] == f"Bearer {TOKEN_2}"


def test_margem_maior_que_validade_nao_gera_token_por_chamada(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1, expires_in=100))
    servidor.enfileirar(ROTA, resposta_pagina([], False), resposta_pagina([], False))
    client = novo_client(token_renew_margin_seconds=300)

    client.consultar(ROTA, REQ)
    client.consultar(ROTA, REQ)

    assert len(servidor.chamadas(TOKEN_PATH)) == 1


def test_401_no_servico_renova_token_e_repete_uma_vez(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1), resposta_token(TOKEN_2))
    servidor.enfileirar(ROTA, httpx2.Response(401), resposta_pagina([{"id": 9}], False))

    resultado = novo_client().consultar(ROTA, REQ)

    assert resultado["registros_teste"] == [{"id": 9}]
    auth = [r.headers["authorization"] for r in servidor.chamadas(ROTA)]
    assert auth == [f"Bearer {TOKEN_1}", f"Bearer {TOKEN_2}"]


def test_401_repetido_desiste_apos_uma_renovacao(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1), resposta_token(TOKEN_2))
    servidor.enfileirar(ROTA, httpx2.Response(401), httpx2.Response(401))

    with pytest.raises(ErpApiNaoAutorizadoError) as exc:
        novo_client().consultar(ROTA, REQ)

    assert exc.value.status_code == 401
    assert len(servidor.chamadas(TOKEN_PATH)) == 2
    assert len(servidor.chamadas(ROTA)) == 2


def test_401_no_endpoint_de_token_nao_repete(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, httpx2.Response(401, json={"error": "invalid_grant"}))

    with pytest.raises(ErpApiNaoAutorizadoError) as exc:
        novo_client().consultar(ROTA, REQ)

    assert exc.value.rota == TOKEN_PATH
    assert len(servidor.requisicoes) == 1


@pytest.mark.parametrize(
    "corpo",
    [{"token_type": "bearer"}, {"access_token": ""}, {"access_token": "x", "expires_in": -5}],
)
def test_resposta_de_token_invalida(novo_client, servidor, corpo):
    servidor.enfileirar(TOKEN_PATH, httpx2.Response(200, json=corpo))

    with pytest.raises(ErpApiRespostaInvalidaError) as exc:
        novo_client().autenticar()
    assert exc.value.__cause__ is None


def test_invalidar_token_forca_novo_pedido(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1), resposta_token(TOKEN_2))
    servidor.enfileirar(ROTA, resposta_pagina([], False), resposta_pagina([], False))
    client = novo_client()

    client.consultar(ROTA, REQ)
    client.invalidar_token()
    client.consultar(ROTA, REQ)

    assert len(servidor.chamadas(TOKEN_PATH)) == 2


@pytest.mark.parametrize(
    "status,classe,transitorio",
    [
        (400, ErpApiRequisicaoInvalidaError, False),
        (403, ErpApiAcessoNegadoError, False),
        (404, ErpApiNaoEncontradoError, False),
        (429, ErpApiLimiteRequisicoesError, True),
        (500, ErpApiErroServidorError, True),
        (502, ErpApiErroServidorError, True),
        (503, ErpApiErroServidorError, True),
        (302, ErpApiHttpError, False),
        (409, ErpApiHttpError, False),
    ],
)
def test_status_de_erro_vira_excecao_especifica(novo_client, servidor, status, classe, transitorio):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(
        ROTA, httpx2.Response(status, text="motivo do erro", headers={"Location": "/x"})
    )

    with pytest.raises(classe) as exc:
        novo_client().consultar(ROTA, REQ)

    assert type(exc.value) is classe
    assert exc.value.status_code == status
    assert exc.value.rota == ROTA
    assert exc.value.transitorio is transitorio
    assert exc.value.detalhe == "motivo do erro"

    assert len(servidor.chamadas(TOKEN_PATH)) == 1


def test_redirect_nao_e_seguido(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, httpx2.Response(302, headers={"Location": "https://outro.invalid/"}))

    with pytest.raises(ErpApiHttpError):
        novo_client().consultar(ROTA, REQ)
    assert len(servidor.requisicoes) == 2


@pytest.mark.parametrize("valor,esperado", [("30", 30.0), ("abc", None), (None, None)])
def test_429_expoe_retry_after(novo_client, servidor, valor, esperado):
    headers = {"Retry-After": valor} if valor is not None else {}
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, httpx2.Response(429, headers=headers))

    with pytest.raises(ErpApiLimiteRequisicoesError) as exc:
        novo_client().consultar(ROTA, REQ)
    assert exc.value.retry_after == esperado


def test_detalhe_do_erro_e_truncado(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, httpx2.Response(400, text="x" * 5000))

    with pytest.raises(ErpApiRequisicaoInvalidaError) as exc:
        novo_client().consultar(ROTA, REQ)
    assert len(exc.value.detalhe) == 300


@pytest.mark.parametrize(
    "falha,classe",
    [
        (httpx2.ReadTimeout("lento"), ErpApiTimeoutError),
        (httpx2.ConnectTimeout("lento"), ErpApiTimeoutError),
        (httpx2.ConnectError("recusada"), ErpApiConexaoError),
        (httpx2.RemoteProtocolError("quebrou"), ErpApiConexaoError),
    ],
)
def test_falhas_de_rede_no_servico(novo_client, servidor, falha, classe):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, falha)

    with pytest.raises(classe) as exc:
        novo_client().consultar(ROTA, REQ)
    assert exc.value.transitorio is True
    assert exc.value.__cause__ is None


def test_timeout_no_endpoint_de_token(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, httpx2.ReadTimeout("lento"))

    with pytest.raises(ErpApiTimeoutError) as exc:
        novo_client().consultar(ROTA, REQ)
    assert exc.value.rota == TOKEN_PATH


@pytest.mark.parametrize(
    "resposta",
    [httpx2.Response(200, text="<html>nao e json</html>"), httpx2.Response(200, json=[1, 2])],
)
def test_resposta_2xx_que_nao_e_objeto_json(novo_client, servidor, resposta):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, resposta)

    with pytest.raises(ErpApiRespostaInvalidaError):
        novo_client().consultar(ROTA, REQ)


def test_iterar_paginas_ate_has_next_falso(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(
        ROTA,
        resposta_pagina([{"id": 1}], True, total=3),
        resposta_pagina([{"id": 2}], True, total=3),
        resposta_pagina([{"id": 3}], False, total=3),
    )
    clausula = Clausula(campo="c", operador=Operador.LIKE, valor="a%")

    paginas = list(
        novo_client().iterar_paginas(ROTA, [clausula], campo_registros="registros_teste")
    )

    assert [p.pagina for p in paginas] == [1, 2, 3]
    assert [r["id"] for p in paginas for r in p.registros] == [1, 2, 3]
    corpos = [corpo_json(r) for r in servidor.chamadas(ROTA)]
    assert [c["page"] for c in corpos] == [1, 2, 3]
    assert all(c["clausulas"] == [clausula.to_payload()] for c in corpos)


def test_iterar_paginas_para_em_pagina_vazia(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, resposta_pagina([{"id": 1}], True), resposta_pagina([], True))

    paginas = list(novo_client().iterar_paginas(ROTA, campo_registros="registros_teste"))

    assert len(paginas) == 2


def test_iterar_paginas_levanta_ao_atingir_o_teto(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, *[resposta_pagina([{"id": 1}], True)] * 2)
    lidas = []

    with pytest.raises(ErpApiPaginacaoExcedidaError):
        for p in novo_client().iterar_paginas(
            ROTA, campo_registros="registros_teste", max_paginas=2
        ):
            lidas.append(p)

    assert len(lidas) == 2


def test_nenhum_segredo_aparece_em_log_ou_excecao(novo_client, servidor, caplog):
    eco = f"recebi password={SENHA} client_secret={CLIENT_SECRET} token={TOKEN_1}"
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1), resposta_token(TOKEN_2))
    servidor.enfileirar(
        ROTA,
        resposta_pagina([], False),
        httpx2.Response(401, text=eco),
        httpx2.Response(400, text=eco),
    )
    client = novo_client(base_url="http://erpapi.teste.invalid")
    caplog.set_level(logging.DEBUG)

    client.consultar(ROTA, REQ)
    with pytest.raises(ErpApiRequisicaoInvalidaError) as exc:
        client.consultar(ROTA, REQ)

    textos = [caplog.text, str(exc.value), repr(client)]
    for segredo in (SENHA, CLIENT_SECRET, TOKEN_1, TOKEN_2):
        for texto in textos:
            assert segredo not in texto
    assert "***" in str(exc.value)

    assert "erpapi.token.obtido" in caplog.text
    assert "erpapi.token.renovacao" in caplog.text
    assert "erpapi.conexao.sem_tls" in caplog.text
    assert f"erpapi.requisicao metodo=POST rota={ROTA}" in caplog.text


def test_filtro_mascara_segredo_mesmo_se_alguem_logar_por_engano(novo_client, caplog):
    novo_client()
    caplog.set_level(logging.INFO)

    logging.getLogger("app.erp.erpapi").info("descuido: senha=%s", SENHA)

    assert SENHA not in caplog.text
    assert "descuido: senha=***" in caplog.text


def test_log_recusa_campo_fora_da_lista():
    from app.erp.logs import registrar

    with pytest.raises(ValueError):
        registrar(logging.INFO, "teste", password="x")


def test_http_sem_tls_e_recusado_em_producao(novo_client, servidor):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    client = novo_client(base_url="http://erpapi.teste.invalid", app_env="producao")

    with pytest.raises(ErpApiConfiguracaoError, match="ERPAPI_PERMITIR_HTTP"):
        client.consultar(ROTA, REQ)


def test_http_em_producao_so_com_permissao_explicita(novo_client, servidor, caplog):
    servidor.enfileirar(TOKEN_PATH, resposta_token(TOKEN_1))
    servidor.enfileirar(ROTA, resposta_pagina([], False))
    client = novo_client(
        base_url="http://erpapi.teste.invalid", app_env="producao", permitir_http=True
    )
    caplog.set_level(logging.WARNING)

    client.consultar(ROTA, REQ)

    assert "erpapi.conexao.sem_tls" in caplog.text
