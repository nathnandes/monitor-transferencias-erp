from collections.abc import Iterable, Iterator
from typing import Any, Protocol, runtime_checkable

from app.erp.schemas import Clausula, RequisicaoPaginada, RespostaPaginada


@runtime_checkable
class ProvedorToken(Protocol):
    def autenticar(self) -> None: ...

    def invalidar_token(self) -> None: ...


@runtime_checkable
class ConsultorErpApi(Protocol):
    def consultar(self, rota: str, requisicao: RequisicaoPaginada) -> dict[str, Any]: ...

    def consultar_pagina(
        self, rota: str, requisicao: RequisicaoPaginada, *, campo_registros: str
    ) -> RespostaPaginada: ...

    def iterar_paginas(
        self,
        rota: str,
        clausulas: Iterable[Clausula] = (),
        *,
        campo_registros: str,
        max_paginas: int | None = None,
    ) -> Iterator[RespostaPaginada]: ...

    def close(self) -> None: ...


@runtime_checkable
class ClienteErpApi(ConsultorErpApi, ProvedorToken, Protocol):
    pass
