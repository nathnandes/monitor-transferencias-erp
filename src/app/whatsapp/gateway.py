import httpx2

from app.notifications.enviador import ErroEnvio
from app.notifications.mensagens import LIMITE_CARACTERES

LIMITE_TEXTO_GATEWAY = 4096


class WhatsAppGatewayEnviador:
    canal = "whatsapp"

    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: float = 15.0,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._base = url.rstrip("/")
        self._http = httpx2.Client(
            timeout=httpx2.Timeout(timeout),
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )

    def __repr__(self) -> str:
        return f"<WhatsAppGatewayEnviador url={self._base}>"

    def close(self) -> None:
        self._http.close()

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        if not chat_id:
            raise ErroEnvio("destino de WhatsApp sem número", transitorio=False)
        corpo = {"numero": chat_id, "texto": texto[: min(LIMITE_CARACTERES, LIMITE_TEXTO_GATEWAY)]}
        try:
            resposta = self._http.post(f"{self._base}/enviar", json=corpo)
        except httpx2.TimeoutException:
            raise ErroEnvio(
                "timeout ao falar com o gateway do WhatsApp", transitorio=True
            ) from None
        except httpx2.TransportError as erro:
            raise ErroEnvio(
                f"gateway do WhatsApp fora do ar ({type(erro).__name__})", transitorio=True
            ) from None

        if resposta.status_code == 200:
            return
        transitorio = resposta.status_code == 429 or resposta.status_code >= 500
        raise ErroEnvio(
            f"gateway do WhatsApp respondeu {resposta.status_code}: {_descricao(resposta)}",
            transitorio=transitorio,
        )


def _descricao(resposta: httpx2.Response) -> str:
    try:
        dados = resposta.json()
    except ValueError:
        return "resposta sem JSON"
    erro = dados.get("erro") if isinstance(dados, dict) else None
    return str(erro)[:200] if erro else "sem descricao"
