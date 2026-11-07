import json

import httpx2
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.notifications.enviador import ErroEnvio
from app.whatsapp.cliente import WhatsAppConfigInvalida, criar_enviador
from app.whatsapp.gateway import WhatsAppGatewayEnviador

TOKEN = "token-do-gateway-de-teste-123456"
URL = "http://whatsapp-gateway:3100"


def _enviador(responder) -> tuple[WhatsAppGatewayEnviador, list[httpx2.Request]]:
    pedidos: list[httpx2.Request] = []

    def _handler(request: httpx2.Request) -> httpx2.Response:
        pedidos.append(request)
        return responder(request)

    return WhatsAppGatewayEnviador(URL, TOKEN, transport=httpx2.MockTransport(_handler)), pedidos


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, whatsapp_enabled=True, whatsapp_provedor="baileys", **kw)  # type: ignore[call-arg]


def test_provedor_baileys_cria_o_enviador_do_gateway_sem_expor_token():
    enviador = criar_enviador(
        _settings(whatsapp_gateway_url=URL, whatsapp_gateway_token=SecretStr(TOKEN))
    )
    assert isinstance(enviador, WhatsAppGatewayEnviador)
    assert TOKEN not in repr(enviador)
    enviador.close()


def test_provedor_baileys_sem_token_ou_com_token_curto_e_erro_de_configuracao():
    with pytest.raises(WhatsAppConfigInvalida):
        criar_enviador(_settings())
    with pytest.raises(WhatsAppConfigInvalida):
        criar_enviador(_settings(whatsapp_gateway_token=SecretStr("curto")))


def test_provedor_meta_continua_sendo_o_padrao():
    assert Settings(_env_file=None).whatsapp_provedor == "meta"  # type: ignore[call-arg]


def test_envia_numero_e_texto_com_o_token_no_cabecalho():
    enviador, pedidos = _enviador(lambda _r: httpx2.Response(200, json={"id": "ABC"}))
    enviador.enviar("Alerta\nlinha 2", "5511999990000")
    (pedido,) = pedidos
    assert str(pedido.url) == f"{URL}/enviar"
    assert pedido.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(pedido.content) == {"numero": "5511999990000", "texto": "Alerta\nlinha 2"}


def test_sem_numero_nao_chama_o_gateway():
    enviador, pedidos = _enviador(lambda _r: httpx2.Response(200, json={}))
    with pytest.raises(ErroEnvio) as erro:
        enviador.enviar("oi", None)
    assert erro.value.transitorio is False
    assert pedidos == []


@pytest.mark.parametrize(
    ("status", "transitorio"),
    [(503, True), (502, True), (500, True), (429, True), (422, False), (401, False), (400, False)],
)
def test_classifica_os_erros_do_gateway(status, transitorio):
    enviador, _ = _enviador(lambda _r: httpx2.Response(status, json={"erro": "motivo"}))
    with pytest.raises(ErroEnvio) as erro:
        enviador.enviar("oi", "5511999990000")
    assert erro.value.transitorio is transitorio
    assert "motivo" in str(erro.value)
    assert TOKEN not in str(erro.value)


def test_gateway_fora_do_ar_e_transitorio():
    def _cai(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("recusado", request=request)

    enviador, _ = _enviador(_cai)
    with pytest.raises(ErroEnvio) as erro:
        enviador.enviar("oi", "5511999990000")
    assert erro.value.transitorio is True
