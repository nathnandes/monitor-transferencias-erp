from typing import Protocol


class ErroEnvio(Exception):
    def __init__(self, mensagem: str, *, transitorio: bool) -> None:
        super().__init__(mensagem)
        self.transitorio = transitorio


class Enviador(Protocol):
    canal: str

    def enviar(self, texto: str, chat_id: str | None = None) -> None: ...
