import httpx2

from app.core.config import Settings
from app.core.logging_config import get_logger
from app.notifications.enviador import ErroEnvio
from app.notifications.mensagens import LIMITE_CARACTERES

logger = get_logger(__name__)

API_URL = "https://api.telegram.org"


class TelegramConfigInvalida(ValueError):
    pass


class TelegramEnviador:
    canal = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        timeout: float = 10.0,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._url = f"{API_URL}/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._http = httpx2.Client(timeout=httpx2.Timeout(timeout), transport=transport)

    def __repr__(self) -> str:
        return f"<TelegramEnviador chat={self._chat_id}>"

    def close(self) -> None:
        self._http.close()

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        corpo = {
            "chat_id": chat_id or self._chat_id,
            "text": texto[:LIMITE_CARACTERES],
            "disable_web_page_preview": True,
        }
        try:
            resposta = self._http.post(self._url, json=corpo)
        except httpx2.TimeoutException:
            raise ErroEnvio("timeout ao falar com o Telegram", transitorio=True) from None
        except httpx2.TransportError as erro:
            raise ErroEnvio(
                f"falha de rede ao falar com o Telegram ({type(erro).__name__})", transitorio=True
            ) from None

        if resposta.status_code == 200:
            return
        descricao = _descricao(resposta)
        transitorio = resposta.status_code == 429 or resposta.status_code >= 500
        raise ErroEnvio(
            f"Telegram respondeu {resposta.status_code}: {descricao}", transitorio=transitorio
        )


def _descricao(resposta: httpx2.Response) -> str:
    try:
        dados = resposta.json()
    except ValueError:
        return "resposta sem JSON"
    descricao = dados.get("description") if isinstance(dados, dict) else None
    return str(descricao)[:200] if descricao else "sem descricao"


def criar_enviador(
    settings: Settings, transport: httpx2.BaseTransport | None = None
) -> TelegramEnviador | None:
    if not settings.telegram_enabled:
        return None
    token = settings.telegram_bot_token.get_secret_value()
    if not token or not settings.telegram_chat_id:
        raise TelegramConfigInvalida(
            "TELEGRAM_ENABLED=true exige TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID"
        )
    return TelegramEnviador(
        token,
        settings.telegram_chat_id,
        timeout=settings.telegram_timeout_seconds,
        transport=transport,
    )
