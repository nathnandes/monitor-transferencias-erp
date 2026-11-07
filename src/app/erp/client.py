import logging
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any, Self

import httpx2
from pydantic import SecretStr, ValidationError

from app.erp.config import ErpApiSettings, get_erpapi_settings
from app.erp.errors import (
    ErpApiAcessoNegadoError,
    ErpApiConexaoError,
    ErpApiConfiguracaoError,
    ErpApiDesabilitadoError,
    ErpApiErroServidorError,
    ErpApiHttpError,
    ErpApiLimiteRequisicoesError,
    ErpApiNaoAutorizadoError,
    ErpApiNaoEncontradoError,
    ErpApiPaginacaoExcedidaError,
    ErpApiRequisicaoInvalidaError,
    ErpApiRespostaInvalidaError,
    ErpApiRotaNaoPermitidaError,
    ErpApiTimeoutError,
)
from app.erp.logs import MASCARADOR, registrar
from app.erp.schemas import (
    Clausula,
    PedidoToken,
    RequisicaoPaginada,
    RespostaPaginada,
    TokenResposta,
    cabecalho_autorizacao,
    interpretar_pagina,
)
from app.erp.token import ArmazemToken

_LIMITE_DETALHE = 300


class _TransporteBloqueado(httpx2.BaseTransport):
    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        raise ErpApiDesabilitadoError(
            "ERPAPI_ENABLED=false; transporte bloqueado", rota=request.url.path
        )


_ERROS_POR_STATUS: dict[int, type[ErpApiHttpError]] = {
    400: ErpApiRequisicaoInvalidaError,
    401: ErpApiNaoAutorizadoError,
    403: ErpApiAcessoNegadoError,
    404: ErpApiNaoEncontradoError,
}


class ErpApiClient:
    def __init__(
        self,
        settings: ErpApiSettings | None = None,
        *,
        transport: httpx2.BaseTransport | None = None,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings or get_erpapi_settings()
        self._relogio = relogio
        self._token = ArmazemToken(relogio, self._settings.token_renew_margin_seconds)
        self._lock_token = threading.Lock()
        self._aviso_http_emitido = False

        MASCARADOR.registrar(self._settings.password.get_secret_value())
        MASCARADOR.registrar(self._settings.client_secret.get_secret_value())

        if not self._settings.enabled:
            transport = _TransporteBloqueado()

        self._http = httpx2.Client(
            base_url=self._settings.base_url.rstrip("/"),
            timeout=httpx2.Timeout(self._settings.timeout_seconds),
            verify=self._settings.verify_ssl,
            transport=transport,
            follow_redirects=False,
            headers={"Accept": "application/json"},
        )

    def autenticar(self) -> None:
        self._verificar_configuracao()
        with self._lock_token:
            self._token.invalidar()
            self._pedir_token()

    def invalidar_token(self) -> None:
        with self._lock_token:
            self._token.invalidar()

    def consultar(self, rota: str, requisicao: RequisicaoPaginada) -> dict[str, Any]:
        self._verificar_configuracao()
        self._validar_rota(rota)

        for tentativa in (1, 2):
            token = self._obter_token()
            try:
                resposta = self._enviar(
                    rota,
                    json=requisicao.to_payload(),
                    headers=cabecalho_autorizacao(token),
                    pagina=requisicao.pagina,
                )
            except ErpApiNaoAutorizadoError:
                if tentativa == 2:
                    raise
                registrar(logging.INFO, "token.renovacao", motivo="401", rota=rota)
                self._descartar_se_atual(token)
                continue
            return self._json_objeto(resposta, rota)

        raise AssertionError("inalcancavel")  # pragma: no cover

    def consultar_pagina(
        self, rota: str, requisicao: RequisicaoPaginada, *, campo_registros: str
    ) -> RespostaPaginada:
        payload = self.consultar(rota, requisicao)
        try:
            pagina = interpretar_pagina(
                payload,
                pagina=requisicao.pagina,
                campo_registros=campo_registros,
                campo_total=self._settings.campo_total,
                campo_tem_proxima=self._settings.campo_tem_proxima,
            )
        except ErpApiRespostaInvalidaError as exc:
            exc.rota = exc.rota or rota
            raise
        registrar(
            logging.DEBUG,
            "pagina.lida",
            rota=rota,
            pagina=pagina.pagina,
            registros=len(pagina.registros),
            tem_proxima=pagina.tem_proxima,
        )
        return pagina

    def iterar_paginas(
        self,
        rota: str,
        clausulas: Iterable[Clausula] = (),
        *,
        campo_registros: str,
        max_paginas: int | None = None,
    ) -> Iterator[RespostaPaginada]:
        teto = max_paginas or self._settings.max_pages
        requisicao = RequisicaoPaginada(pagina=1, clausulas=tuple(clausulas))
        for _ in range(teto):
            pagina = self.consultar_pagina(rota, requisicao, campo_registros=campo_registros)
            yield pagina
            if not pagina.tem_proxima or not pagina.registros:
                return
            requisicao = requisicao.proxima()
        registrar(logging.WARNING, "paginacao.excedida", rota=rota, pagina=teto)
        raise ErpApiPaginacaoExcedidaError(f"limite de {teto} paginas atingido", rota=rota)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"ErpApiClient(base_url={self._settings.base_url!r}, token={self._token!r})"

    def _verificar_configuracao(self) -> None:
        s = self._settings
        if not s.enabled:
            raise ErpApiDesabilitadoError("ERPAPI_ENABLED=false; nenhuma chamada e feita")
        faltando = s.campos_obrigatorios_ausentes()
        if faltando:
            raise ErpApiConfiguracaoError(f"variaveis ausentes: {', '.join(faltando)}")
        if not s.base_url.startswith(("http://", "https://")):
            raise ErpApiConfiguracaoError("ERPAPI_BASE_URL deve comecar com http:// ou https://")
        if not s.token_path.startswith("/"):
            raise ErpApiConfiguracaoError("ERPAPI_TOKEN_PATH deve comecar com /")
        if s.base_url.startswith("http://") and s.producao and not s.permitir_http:
            raise ErpApiConfiguracaoError(
                "ERPAPI_BASE_URL com http:// em producao: credenciais e token trafegariam "
                "sem criptografia. Use https:// ou, se for uma decisao registrada, "
                "ERPAPI_PERMITIR_HTTP=true"
            )
        if s.base_url.startswith("http://") and not self._aviso_http_emitido:
            self._aviso_http_emitido = True
            registrar(
                logging.WARNING,
                "conexao.sem_tls",
                base_url=s.base_url,
                motivo="credenciais e token trafegam sem criptografia",
            )

    def _validar_rota(self, rota: str) -> None:

        invalida = (
            not rota.startswith("/")
            or rota.startswith("//")
            or "://" in rota
            or any(c in rota for c in "?#\\")
            or ".." in rota
        )
        if invalida:
            raise ErpApiRotaNaoPermitidaError("rota com formato invalido", rota=rota)
        if rota == self._settings.token_path:
            raise ErpApiRotaNaoPermitidaError("rota de token nao e servico", rota=rota)
        if rota not in self._settings.rotas_permitidas:
            raise ErpApiRotaNaoPermitidaError("rota fora de ERPAPI_ALLOWED_ROUTES", rota=rota)

    def _obter_token(self) -> SecretStr:
        token = self._token.valido()
        if token is not None:
            return token
        with self._lock_token:
            token = self._token.valido()
            if token is None:
                token = self._pedir_token()
            return token

    def _descartar_se_atual(self, token: SecretStr) -> None:
        with self._lock_token:
            atual = self._token.valido()
            if atual is not None and atual.get_secret_value() == token.get_secret_value():
                self._token.invalidar()

    def _pedir_token(self) -> SecretStr:
        s = self._settings
        pedido = PedidoToken(
            client_id=s.client_id,
            client_secret=s.client_secret,
            username=s.username,
            password=s.password,
        )
        resposta = self._enviar(s.token_path, data=pedido.to_form())
        corpo = self._json_objeto(resposta, s.token_path)
        try:
            dados = TokenResposta.model_validate(corpo)
        except ValidationError:
            raise ErpApiRespostaInvalidaError(
                "resposta de token sem access_token valido", rota=s.token_path
            ) from None

        MASCARADOR.registrar(dados.access_token.get_secret_value())
        validade = dados.expires_in or s.token_ttl_fallback_seconds
        self._token.guardar(dados.access_token, validade)
        registrar(
            logging.INFO,
            "token.obtido",
            validade_s=validade,
            motivo="expires_in" if dados.expires_in else "fallback",
        )
        return dados.access_token

    def _enviar(self, rota: str, *, pagina: int | None = None, **kwargs: Any) -> httpx2.Response:

        if not self._settings.enabled:
            raise ErpApiDesabilitadoError("ERPAPI_ENABLED=false; nenhuma chamada e feita")
        inicio = self._relogio()
        campos: dict[str, Any] = {"metodo": "POST", "rota": rota}
        if pagina is not None:
            campos["pagina"] = pagina
        try:
            resposta = self._http.post(rota, **kwargs)
        except httpx2.TimeoutException as exc:
            registrar(logging.WARNING, "requisicao.falha", **campos, erro=type(exc).__name__)
            raise ErpApiTimeoutError("tempo esgotado", rota=rota) from None
        except httpx2.TransportError as exc:
            registrar(logging.WARNING, "requisicao.falha", **campos, erro=type(exc).__name__)
            raise ErpApiConexaoError(
                f"falha de conexao ({type(exc).__name__})", rota=rota
            ) from None

        duracao_ms = round((self._relogio() - inicio) * 1000)
        nivel = logging.INFO if resposta.is_success else logging.WARNING
        registrar(nivel, "requisicao", **campos, status=resposta.status_code, duracao_ms=duracao_ms)
        self._verificar_status(resposta, rota)
        return resposta

    def _verificar_status(self, resposta: httpx2.Response, rota: str) -> None:
        status = resposta.status_code
        if 200 <= status < 300:
            return

        detalhe = MASCARADOR.mascarar(resposta.text[:_LIMITE_DETALHE]) or None
        comum: dict[str, Any] = {"rota": rota, "status_code": status, "detalhe": detalhe}

        if status == 429:
            raise ErpApiLimiteRequisicoesError(
                "limite de requisicoes excedido",
                retry_after=_retry_after(resposta),
                **comum,
            )
        if status >= 500:
            raise ErpApiErroServidorError("erro no servidor ERPAPI", **comum)
        classe = _ERROS_POR_STATUS.get(status, ErpApiHttpError)
        raise classe("resposta HTTP de erro", **comum)

    @staticmethod
    def _json_objeto(resposta: httpx2.Response, rota: str) -> dict[str, Any]:
        try:
            corpo = resposta.json()
        except ValueError:
            raise ErpApiRespostaInvalidaError("resposta nao e JSON", rota=rota) from None
        if not isinstance(corpo, dict):
            raise ErpApiRespostaInvalidaError("resposta JSON nao e um objeto", rota=rota)
        return corpo


def _retry_after(resposta: httpx2.Response) -> float | None:
    valor = resposta.headers.get("Retry-After")
    if valor is None:
        return None
    try:
        return max(0.0, float(valor))
    except ValueError:
        return None
