import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import IntegracaoErro, Sincronizacao
from app.erp.errors import (
    ErpApiConexaoError,
    ErpApiConfiguracaoError,
    ErpApiError,
    ErpApiLimiteRequisicoesError,
    ErpApiNaoAutorizadoError,
    ErpApiPaginacaoExcedidaError,
    ErpApiTimeoutError,
)
from app.erp.schemas import RespostaPaginada

logger = get_logger(__name__)

FabricaSessao = Callable[[], Session]


_LOCK_SINCRONIZACAO = 726_100_001

_LIMITE_MENSAGEM = 2000

_FALHAS_GERAIS: tuple[type[ErpApiError], ...] = (
    ErpApiConfiguracaoError,
    ErpApiNaoAutorizadoError,
    ErpApiTimeoutError,
    ErpApiConexaoError,
)


def eh_falha_geral(exc: ErpApiError) -> bool:
    return isinstance(exc, _FALHAS_GERAIS)


class FalhaGeralError(Exception):
    def __init__(self, causa: ErpApiError) -> None:
        self.causa = causa
        super().__init__(resumir(causa))


def resumir(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:_LIMITE_MENSAGEM]


def agora_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class PoliticaRetry:
    tentativas: int = 3
    espera_segundos: float = 2.0

    dormir: Callable[[float], None] = field(default=time.sleep, repr=False)

    def espera(self, tentativa: int, exc: ErpApiError) -> float:
        if isinstance(exc, ErpApiLimiteRequisicoesError) and exc.retry_after is not None:
            return min(exc.retry_after, 300.0)
        return float(self.espera_segundos * (2 ** (tentativa - 1)))


AoFalhar = Callable[[ErpApiError, int], None]


def com_retry[T](chamada: Callable[[], T], politica: PoliticaRetry, ao_falhar: AoFalhar) -> T:
    for tentativa in range(1, politica.tentativas + 1):
        try:
            return chamada()
        except ErpApiError as exc:
            ao_falhar(exc, tentativa)
            if not exc.transitorio or tentativa >= politica.tentativas:
                raise
            politica.dormir(politica.espera(tentativa, exc))
    raise AssertionError("inalcancavel")  # pragma: no cover


@dataclass
class Leitura:
    registros: list[dict[str, Any]] = field(default_factory=list)
    paginas: int = 0


def _falhou_na_pagina(
    ao_falhar: Callable[[ErpApiError, int, int], None],
    pagina: int,
    exc: ErpApiError,
    tentativa: int,
) -> None:
    ao_falhar(exc, tentativa, pagina)


def percorrer_paginas(
    buscar: Callable[[int], RespostaPaginada],
    *,
    max_paginas: int,
    politica: PoliticaRetry,
    ao_falhar: Callable[[ErpApiError, int, int], None],
    leitura: Leitura | None = None,
) -> Leitura:
    leitura = leitura if leitura is not None else Leitura()
    for numero in range(1, max_paginas + 1):
        pagina = com_retry(
            partial(buscar, numero),
            politica,
            partial(_falhou_na_pagina, ao_falhar, numero),
        )
        leitura.paginas += 1
        leitura.registros.extend(pagina.registros)
        if not pagina.tem_proxima or not pagina.registros:
            return leitura
    raise ErpApiPaginacaoExcedidaError(f"limite de {max_paginas} paginas atingido")


def iniciar_execucao(
    fabrica: FabricaSessao,
    tipo: str,
    *,
    empresa_id: int | None = None,
    pai_id: int | None = None,
) -> int:
    with fabrica() as db, db.begin():
        execucao = Sincronizacao(
            tipo=tipo,
            empresa_id=empresa_id,
            sincronizacao_pai_id=pai_id,
            status="em_andamento",
            inicio=agora_utc(),
        )
        db.add(execucao)
        db.flush()
        return execucao.id


def finalizar_execucao(
    db: Session, execucao_id: int, status: str, *, mensagem: str | None = None, **contadores: int
) -> None:
    db.execute(
        update(Sincronizacao)
        .where(Sincronizacao.id == execucao_id)
        .values(
            status=status,
            fim=agora_utc(),
            mensagem_erro=mensagem[:_LIMITE_MENSAGEM] if mensagem else None,
            **contadores,
        )
    )


def finalizar_execucao_isolada(
    fabrica: FabricaSessao,
    execucao_id: int,
    status: str,
    *,
    mensagem: str | None = None,
    **contadores: int,
) -> None:
    with fabrica() as db, db.begin():
        finalizar_execucao(db, execucao_id, status, mensagem=mensagem, **contadores)


class RegistroErros:
    def __init__(self, fabrica: FabricaSessao, execucao_id: int) -> None:
        self._fabrica = fabrica
        self._execucao_id = execucao_id

    def erpapi(
        self,
        exc: ErpApiError,
        *,
        tentativa: int,
        id_empresa: str | None = None,
        pedido: str | None = None,
    ) -> None:
        mensagem = str(exc)
        if pedido:
            mensagem = f"{mensagem} | pedido: {pedido}"
        logger.warning(
            "sync.falha_erpapi execucao=%s empresa=%s rota=%s status=%s tentativa=%s erro=%s",
            self._execucao_id,
            id_empresa,
            exc.rota,
            exc.status_code,
            tentativa,
            type(exc).__name__,
        )
        self._gravar(
            tipo_erro=type(exc).__name__,
            mensagem=mensagem,
            id_erp_empresa=id_empresa,
            endpoint=exc.rota,
            status_http=exc.status_code,
            tentativa=tentativa,
        )

    def outro(
        self,
        tipo_erro: str,
        mensagem: str,
        *,
        id_empresa: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        logger.warning(
            "sync.falha execucao=%s empresa=%s erro=%s", self._execucao_id, id_empresa, tipo_erro
        )
        self._gravar(
            tipo_erro=tipo_erro,
            mensagem=mensagem,
            id_erp_empresa=id_empresa,
            endpoint=endpoint,
            status_http=None,
            tentativa=1,
        )

    def _gravar(self, *, mensagem: str, endpoint: str | None, **campos: Any) -> None:
        try:
            with self._fabrica() as db, db.begin():
                db.add(
                    IntegracaoErro(
                        sincronizacao_id=self._execucao_id,
                        mensagem=mensagem[:_LIMITE_MENSAGEM],
                        endpoint=endpoint[:200] if endpoint else None,
                        ocorrido_em=agora_utc(),
                        **campos,
                    )
                )
        except Exception:
            logger.exception("sync.registro_erro_falhou execucao=%s", self._execucao_id)


def limitar_cursor(ultima: datetime | None, agora: datetime, onde: str) -> datetime | None:
    if ultima is not None and ultima > agora:
        logger.warning(
            "sync.cursor_no_futuro %s dtalteracao=%s: lendo desde agora (%s)",
            onde,
            ultima.isoformat(),
            agora.isoformat(),
        )
        return agora
    return ultima


@contextmanager
def trava_sincronizacao(fabrica: FabricaSessao) -> Iterator[bool]:
    db = fabrica()
    bind = db.get_bind()
    if isinstance(bind, Engine):
        db.close()
        with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
            obtida = bool(conexao.scalar(select(func.pg_try_advisory_lock(_LOCK_SINCRONIZACAO))))
            try:
                yield obtida
            finally:
                if obtida:
                    conexao.scalar(select(func.pg_advisory_unlock(_LOCK_SINCRONIZACAO)))
        return

    obtida = False
    try:
        obtida = bool(db.scalar(select(func.pg_try_advisory_lock(_LOCK_SINCRONIZACAO))))
        yield obtida
    finally:
        try:
            if obtida:
                db.scalar(select(func.pg_advisory_unlock(_LOCK_SINCRONIZACAO)))

            db.commit()
        finally:
            db.close()
