import threading
import time
from collections import deque
from collections.abc import Callable, Hashable


class LimitadorTentativas:
    def __init__(
        self,
        limite: int,
        janela_segundos: float,
        *,
        relogio: Callable[[], float] = time.monotonic,
        max_chaves: int = 10_000,
    ) -> None:
        self.limite = limite
        self.janela = janela_segundos
        self._relogio = relogio
        self._max_chaves = max_chaves
        self._falhas: dict[Hashable, deque[float]] = {}

        self._trava = threading.Lock()

    def _vivas(self, chave: Hashable, agora: float) -> deque[float] | None:
        falhas = self._falhas.get(chave)
        if falhas is None:
            return None
        while falhas and falhas[0] <= agora - self.janela:
            falhas.popleft()
        if not falhas:
            del self._falhas[chave]
            return None
        return falhas

    def bloqueado(self, chave: Hashable) -> bool:
        with self._trava:
            falhas = self._vivas(chave, self._relogio())
            return falhas is not None and len(falhas) >= self.limite

    def registrar_falha(self, chave: Hashable) -> None:
        with self._trava:
            agora = self._relogio()
            falhas = self._vivas(chave, agora)
            if falhas is None:
                if len(self._falhas) >= self._max_chaves:
                    self._compactar(agora)
                falhas = self._falhas.setdefault(chave, deque())
            falhas.append(agora)

    def limpar(self, chave: Hashable) -> None:
        with self._trava:
            self._falhas.pop(chave, None)

    def _compactar(self, agora: float) -> None:
        for chave in list(self._falhas):
            self._vivas(chave, agora)
        while len(self._falhas) >= self._max_chaves:
            del self._falhas[next(iter(self._falhas))]
