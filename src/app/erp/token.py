from collections.abc import Callable

from pydantic import SecretStr


class ArmazemToken:
    def __init__(self, relogio: Callable[[], float], margem_segundos: int) -> None:
        self._relogio = relogio
        self._margem = margem_segundos
        self._token: SecretStr | None = None
        self._renovar_em: float = 0.0

    def valido(self) -> SecretStr | None:
        if self._token is None or self._relogio() >= self._renovar_em:
            return None
        return self._token

    def guardar(self, token: SecretStr, validade_segundos: int) -> None:

        margem = min(self._margem, validade_segundos // 2)
        self._token = token
        self._renovar_em = self._relogio() + validade_segundos - margem

    def invalidar(self) -> None:
        self._token = None
        self._renovar_em = 0.0

    def __repr__(self) -> str:
        estado = "vazio" if self._token is None else "preenchido"
        return f"ArmazemToken({estado})"
