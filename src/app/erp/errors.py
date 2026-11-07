from typing import Any


class ErpApiError(Exception):
    transitorio: bool = False

    def __init__(
        self,
        mensagem: str,
        *,
        rota: str | None = None,
        status_code: int | None = None,
        detalhe: str | None = None,
    ) -> None:
        self.rota = rota
        self.status_code = status_code
        self.detalhe = detalhe
        partes = [mensagem]
        if rota:
            partes.append(f"rota={rota}")
        if status_code is not None:
            partes.append(f"status={status_code}")
        if detalhe:
            partes.append(f"detalhe={detalhe}")
        super().__init__(" | ".join(partes))


class ErpApiConfiguracaoError(ErpApiError):
    pass


class ErpApiDesabilitadoError(ErpApiConfiguracaoError):
    pass


class ErpApiRotaNaoPermitidaError(ErpApiConfiguracaoError):
    pass


class ErpApiTimeoutError(ErpApiError):
    transitorio = True


class ErpApiConexaoError(ErpApiError):
    transitorio = True


class ErpApiHttpError(ErpApiError):
    pass


class ErpApiRequisicaoInvalidaError(ErpApiHttpError):
    pass


class ErpApiNaoAutorizadoError(ErpApiHttpError):
    pass


class ErpApiAcessoNegadoError(ErpApiHttpError):
    pass


class ErpApiNaoEncontradoError(ErpApiHttpError):
    pass


class ErpApiLimiteRequisicoesError(ErpApiHttpError):
    transitorio = True

    def __init__(self, *args: Any, retry_after: float | None = None, **kwargs: Any) -> None:
        self.retry_after = retry_after
        super().__init__(*args, **kwargs)


class ErpApiErroServidorError(ErpApiHttpError):
    transitorio = True


class ErpApiRespostaInvalidaError(ErpApiError):
    pass


class ErpApiPaginacaoExcedidaError(ErpApiError):
    pass
