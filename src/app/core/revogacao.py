import threading
from collections.abc import Callable
from datetime import UTC, datetime


class TokensRevogados:
    def __init__(
        self,
        *,
        relogio: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_tokens: int = 50_000,
    ) -> None:
        self._relogio = relogio
        self._max = max_tokens
        self._expira: dict[str, datetime] = {}
        self._trava = threading.Lock()

    def revogar(self, jti: str, expira_em: datetime) -> None:
        with self._trava:
            self._limpar()
            if len(self._expira) >= self._max:
                del self._expira[min(self._expira, key=self._expira.__getitem__)]
            self._expira[jti] = expira_em

    def revogado(self, jti: str) -> bool:
        with self._trava:
            expira = self._expira.get(jti)
            return expira is not None and expira > self._relogio()

    def _limpar(self) -> None:
        agora = self._relogio()
        for jti in [j for j, e in self._expira.items() if e <= agora]:
            del self._expira[jti]
