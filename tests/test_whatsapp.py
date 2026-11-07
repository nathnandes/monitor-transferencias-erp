import json
import logging

import httpx2
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging_config import FormatterMascarado
from app.notifications.enviador import ErroEnvio
from app.whatsapp.cliente import (
    LIMITE_VARIAVEL_MODELO,
    WhatsAppConfigInvalida,
    WhatsAppEnviador,
    criar_enviador,
    texto_em_uma_linha,
)

TOKEN = "EAAGm0PX4ZCpsBAKZCZBjZBxyzExemploDeTokenFalso1234567890abcdef"
NUMERO_ID = "100000000000001"


def _enviador(responder, **kw) -> tuple[WhatsAppEnviador, list[httpx2.Request]]:
    pedidos: list[httpx2.Request] = []

    def _handler(request: httpx2.Request) -> httpx2.Response:
        pedidos.append(request)
        return responder(request)

    enviador = WhatsAppEnviador(TOKEN, NUMERO_ID, transport=httpx2.MockTransport(_handler), **kw)
    return enviador, pedidos


def _ok(_request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"messages": [{"id": "wamid.x"}]})


def test_desligado_por_padrao_nao_cria_enviador():
    assert criar_enviador(Settings(_env_file=None)) is None  # type: ignore[call-arg]


def test_ligado_sem_token_ou_numero_e_erro_de_configuracao():
    with pytest.raises(WhatsAppConfigInvalida):
        criar_enviador(Settings(_env_file=None, whatsapp_enabled=True))  # type: ignore[call-arg]
    with pytest.raises(WhatsAppConfigInvalida):
        criar_enviador(
            Settings(  # type: ignore[call-arg]
                _env_file=None, whatsapp_enabled=True, whatsapp_access_token=SecretStr(TOKEN)
            )
        )


def test_ligado_e_configurado_cria_enviador_sem_expor_token():
    enviador = criar_enviador(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr(TOKEN),
            whatsapp_phone_number_id=NUMERO_ID,
        )
    )
    assert enviador is not None
    assert enviador.canal == "whatsapp"
    assert TOKEN not in repr(enviador)
    enviador.close()


def test_envia_texto_livre_ao_numero_do_destino():
    enviador, pedidos = _enviador(_ok)

    enviador.enviar("olá\nlinha 2", chat_id="5511987654321")

    (pedido,) = pedidos
    assert pedido.method == "POST"
    assert pedido.url.host == "graph.facebook.com"
    assert pedido.url.path == f"/v21.0/{NUMERO_ID}/messages"
    assert pedido.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(pedido.read()) == {
        "messaging_product": "whatsapp",
        "to": "5511987654321",
        "type": "text",
        "text": {"body": "olá\nlinha 2", "preview_url": False},
    }


def test_com_modelo_envia_o_texto_na_variavel_em_uma_linha():
    enviador, pedidos = _enviador(_ok, modelo="alerta_erp", idioma="pt_BR")

    enviador.enviar("🚨 Título\n\nNota:\tNF 1     e mais", chat_id="5511987654321")

    corpo = json.loads(pedidos[0].read())
    assert corpo["type"] == "template"
    assert corpo["template"]["name"] == "alerta_erp"
    assert corpo["template"]["language"] == {"code": "pt_BR"}
    (componente,) = corpo["template"]["components"]
    assert componente["type"] == "body"
    assert componente["parameters"] == [{"type": "text", "text": "🚨 Título · Nota: NF 1 e mais"}]


def test_texto_em_uma_linha_respeita_o_limite_do_modelo():
    texto = texto_em_uma_linha("x" * 5000)
    assert len(texto) == LIMITE_VARIAVEL_MODELO
    assert texto.endswith("…")
    assert "\n" not in texto_em_uma_linha("a\nb\r\nc")


def test_destino_sem_numero_e_falha_permanente_sem_rede():
    enviador, pedidos = _enviador(_ok)
    with pytest.raises(ErroEnvio) as info:
        enviador.enviar("x")
    assert info.value.transitorio is False
    assert pedidos == []


@pytest.mark.parametrize(("status", "transitorio"), [(429, True), (503, True), (400, False)])
def test_erros_http_classificados_com_o_codigo_da_meta(status, transitorio):
    enviador, _ = _enviador(
        lambda r: httpx2.Response(
            status,
            json={
                "error": {
                    "message": "(#131030) Recipient phone number not in allowed list",
                    "code": 131030,
                    "error_data": {"details": "adicione o numero na lista de teste"},
                }
            },
        )
    )
    with pytest.raises(ErroEnvio) as info:
        enviador.enviar("x", chat_id="5511987654321")
    assert info.value.transitorio is transitorio
    mensagem = str(info.value)
    assert str(status) in mensagem and "131030" in mensagem and "lista de teste" in mensagem
    assert TOKEN not in mensagem


def test_timeout_e_falha_de_rede_sao_transitorios_e_nao_vazam_token():
    def estoura(request):
        raise httpx2.ReadTimeout("timeout", request=request)

    def recusa(request):
        raise httpx2.ConnectError(f"falhou {request.url} {request.headers}", request=request)

    for responder in (estoura, recusa):
        enviador, _ = _enviador(responder)
        with pytest.raises(ErroEnvio) as info:
            enviador.enviar("x", chat_id="5511987654321")
        assert info.value.transitorio is True
        assert TOKEN not in str(info.value)


def test_token_da_meta_e_mascarado_em_log():
    registro = logging.makeLogRecord(
        {"msg": f"falhou com token {TOKEN} no meio", "levelname": "ERROR"}
    )
    texto = FormatterMascarado("%(message)s").format(registro)
    assert TOKEN not in texto
