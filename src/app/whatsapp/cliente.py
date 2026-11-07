import re

import httpx2

from app.core.config import Settings
from app.core.logging_config import get_logger
from app.notifications.enviador import ErroEnvio
from app.notifications.mensagens import LIMITE_CARACTERES
from app.whatsapp.gateway import WhatsAppGatewayEnviador

logger = get_logger(__name__)

API_URL = "https://graph.facebook.com"

LIMITE_VARIAVEL_MODELO = 900
SEPARADOR_LINHAS = " · "

_ESPACOS = re.compile(r"[ \t]+")


class WhatsAppConfigInvalida(ValueError):
    pass


def texto_em_uma_linha(texto: str) -> str:
    linhas = [_ESPACOS.sub(" ", linha).strip() for linha in texto.splitlines()]
    junto = SEPARADOR_LINHAS.join(linha for linha in linhas if linha)
    if len(junto) > LIMITE_VARIAVEL_MODELO:
        junto = junto[: LIMITE_VARIAVEL_MODELO - 1].rstrip() + "…"
    return junto


class WhatsAppEnviador:
    canal = "whatsapp"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        *,
        api_version: str = "v21.0",
        modelo: str = "",
        idioma: str = "pt_BR",
        timeout: float = 10.0,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._url = f"{API_URL}/{api_version}/{phone_number_id}/messages"
        self._phone_number_id = phone_number_id
        self._modelo = modelo.strip()
        self._idioma = idioma
        self._http = httpx2.Client(
            timeout=httpx2.Timeout(timeout),
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )

    def __repr__(self) -> str:
        return f"<WhatsAppEnviador numero={self._phone_number_id} modelo={self._modelo or '-'}>"

    def close(self) -> None:
        self._http.close()

    def _corpo(self, texto: str, numero: str) -> dict[str, object]:
        if self._modelo:
            return {
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "template",
                "template": {
                    "name": self._modelo,
                    "language": {"code": self._idioma},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": texto_em_uma_linha(texto)}],
                        }
                    ],
                },
            }
        return {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {"body": texto[:LIMITE_CARACTERES], "preview_url": False},
        }

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        if not chat_id:
            raise ErroEnvio("destino de WhatsApp sem número", transitorio=False)
        try:
            resposta = self._http.post(self._url, json=self._corpo(texto, chat_id))
        except httpx2.TimeoutException:
            raise ErroEnvio("timeout ao falar com o WhatsApp", transitorio=True) from None
        except httpx2.TransportError as erro:
            raise ErroEnvio(
                f"falha de rede ao falar com o WhatsApp ({type(erro).__name__})", transitorio=True
            ) from None

        if resposta.status_code == 200:
            return
        descricao = _descricao(resposta)
        transitorio = resposta.status_code == 429 or resposta.status_code >= 500
        raise ErroEnvio(
            f"WhatsApp respondeu {resposta.status_code}: {descricao}", transitorio=transitorio
        )


def _descricao(resposta: httpx2.Response) -> str:
    try:
        dados = resposta.json()
    except ValueError:
        return "resposta sem JSON"
    erro = dados.get("error") if isinstance(dados, dict) else None
    if not isinstance(erro, dict):
        return "sem descricao"
    dados_erro = erro.get("error_data")
    detalhe = dados_erro.get("details") if isinstance(dados_erro, dict) else None
    partes = [
        f"({erro['code']})" if erro.get("code") is not None else "",
        str(erro.get("message") or ""),
        f"- {detalhe}" if detalhe else "",
    ]
    return " ".join(p for p in partes if p)[:200] or "sem descricao"


def criar_enviador(
    settings: Settings, transport: httpx2.BaseTransport | None = None
) -> WhatsAppEnviador | WhatsAppGatewayEnviador | None:
    if not settings.whatsapp_enabled:
        return None
    if settings.whatsapp_provedor == "baileys":
        token_gateway = settings.whatsapp_gateway_token.get_secret_value()
        if len(token_gateway) < 16 or not settings.whatsapp_gateway_url:
            raise WhatsAppConfigInvalida(
                "WHATSAPP_PROVEDOR=baileys exige WHATSAPP_GATEWAY_URL e "
                "WHATSAPP_GATEWAY_TOKEN (>= 16 caracteres)"
            )
        return WhatsAppGatewayEnviador(
            settings.whatsapp_gateway_url,
            token_gateway,
            timeout=max(settings.whatsapp_timeout_seconds, 15.0),
            transport=transport,
        )
    token = settings.whatsapp_access_token.get_secret_value()
    if not token or not settings.whatsapp_phone_number_id:
        raise WhatsAppConfigInvalida(
            "WHATSAPP_ENABLED=true exige WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID"
        )
    return WhatsAppEnviador(
        token,
        settings.whatsapp_phone_number_id,
        api_version=settings.whatsapp_api_version,
        modelo=settings.whatsapp_template,
        idioma=settings.whatsapp_template_idioma,
        timeout=settings.whatsapp_timeout_seconds,
        transport=transport,
    )
