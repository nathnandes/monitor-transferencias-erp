import json
import logging

import httpx2
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging_config import FormatterMascarado
from app.notifications.enviador import ErroEnvio
from app.telegram.cliente import TelegramConfigInvalida, TelegramEnviador, criar_enviador

TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ"


def _enviador(responder) -> tuple[TelegramEnviador, list[httpx2.Request]]:
    pedidos: list[httpx2.Request] = []

    def _handler(request: httpx2.Request) -> httpx2.Response:
        pedidos.append(request)
        return responder(request)

    return TelegramEnviador(TOKEN, "-100123", transport=httpx2.MockTransport(_handler)), pedidos


def test_desligado_por_padrao_nao_cria_enviador():
    assert criar_enviador(Settings(_env_file=None)) is None  # type: ignore[call-arg]


def test_ligado_sem_token_ou_chat_e_erro_de_configuracao():
    with pytest.raises(TelegramConfigInvalida):
        criar_enviador(Settings(_env_file=None, telegram_enabled=True))  # type: ignore[call-arg]
    with pytest.raises(TelegramConfigInvalida):
        criar_enviador(
            Settings(  # type: ignore[call-arg]
                _env_file=None, telegram_enabled=True, telegram_bot_token=SecretStr(TOKEN)
            )
        )


def test_ligado_e_configurado_cria_enviador_sem_expor_token():
    enviador = criar_enviador(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            telegram_enabled=True,
            telegram_bot_token=SecretStr(TOKEN),
            telegram_chat_id="-100123",
        )
    )
    assert enviador is not None
    assert TOKEN not in repr(enviador)
    enviador.close()


def test_envia_para_o_chat_configurado():
    enviador, pedidos = _enviador(lambda r: httpx2.Response(200, json={"ok": True}))

    enviador.enviar("olá")

    (pedido,) = pedidos
    assert pedido.method == "POST"
    assert pedido.url.host == "api.telegram.org"
    assert pedido.url.path == f"/bot{TOKEN}/sendMessage"
    corpo = json.loads(pedido.read())
    assert corpo == {"chat_id": "-100123", "text": "olá", "disable_web_page_preview": True}


@pytest.mark.parametrize(("status", "transitorio"), [(429, True), (502, True), (401, False)])
def test_erros_http_classificados(status, transitorio):
    enviador, _ = _enviador(
        lambda r: httpx2.Response(status, json={"ok": False, "description": "motivo"})
    )
    with pytest.raises(ErroEnvio) as info:
        enviador.enviar("x")
    assert info.value.transitorio is transitorio
    assert str(status) in str(info.value) and "motivo" in str(info.value)
    assert TOKEN not in str(info.value)


def test_timeout_e_transitorio_e_nao_vaza_token():
    def estoura(request):
        raise httpx2.ReadTimeout("timeout", request=request)

    enviador, _ = _enviador(estoura)
    with pytest.raises(ErroEnvio) as info:
        enviador.enviar("x")
    assert info.value.transitorio is True
    assert TOKEN not in str(info.value)


def test_falha_de_conexao_nao_inclui_url_com_token():
    def recusa(request):
        raise httpx2.ConnectError(f"falhou {request.url}", request=request)

    enviador, _ = _enviador(recusa)
    with pytest.raises(ErroEnvio) as info:
        enviador.enviar("x")
    assert info.value.transitorio is True
    assert TOKEN not in str(info.value) and "api.telegram.org" not in str(info.value)


def test_token_do_bot_e_mascarado_em_log():
    registro = logging.makeLogRecord(
        {"msg": f"POST https://api.telegram.org/bot{TOKEN}/sendMessage", "levelname": "INFO"}
    )
    texto = FormatterMascarado("%(message)s").format(registro)
    assert TOKEN not in texto
    assert "/bot***/sendMessage" in texto
