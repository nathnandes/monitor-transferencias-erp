import io
import logging

import pytest

from app.core import logging_config
from app.core.logging_config import FormatterMascarado, setup_logging
from app.core.mascaramento import mascarar_texto
from app.erp.logs import LOGGER_NOME


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("password=abc12345", "password=***"),
        ("SENHA: minhaSenha9", "SENHA: ***"),
        ('{"client_secret": "s3cr3t-valor"}', '{"client_secret": "***"}'),
        ("{'password': 'p@ss-1'}", "{'password': '***'}"),
        ("access_token=tok-123&token_type=bearer", "access_token=***&token_type=bearer"),
        (
            '{"access_token":"eyJhbGciOi.xyz","expires_in":86399}',
            '{"access_token":"***","expires_in":86399}',
        ),
        ("refresh_token=r-999", "refresh_token=***"),
        ("token: abcdef123", "token: ***"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.x.y", "Authorization: Bearer ***"),
        ("{'Authorization': 'Basic dXNlcjpwYXNz'}", "{'Authorization': 'Basic ***'}"),
        ("authorization=abcdef", "authorization=***"),
        ("enviado com bearer 0123456789abcdef", "enviado com bearer ***"),
        (
            "postgresql+psycopg://erp:minhasenha@localhost:5432/db",
            "postgresql+psycopg://erp:***@localhost:5432/db",
        ),
        (
            "client_id=cli&client_secret=cs-1&grant_type=password",
            "client_id=cli&client_secret=***&grant_type=password",
        ),
    ],
)
def test_mascara_valor_de_chave_sensivel(entrada, esperado):
    assert mascarar_texto(entrada) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "token_type=bearer",
        "token_renew_margin_seconds=300",
        "erpapi.token.obtido validade_s=3600 motivo=expires_in",
        "erpapi.requisicao metodo=POST rota=/teste/servico status=200 duracao_ms=12",
        "variaveis ausentes: ERPAPI_PASSWORD, ERPAPI_CLIENT_SECRET",
        "https://host.invalid:8443/caminho",
        "",
    ],
)
def test_nao_altera_texto_sem_segredo(texto):
    assert mascarar_texto(texto) == texto


def _logger_isolado(nome: str) -> tuple[logging.Logger, io.StringIO]:
    saida = io.StringIO()
    handler = logging.StreamHandler(saida)
    handler.setFormatter(FormatterMascarado("%(levelname)s %(name)s | %(message)s"))
    logger = logging.getLogger(nome)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger, saida


def test_formatter_mascara_mensagem_argumentos_e_traceback():
    logger, saida = _logger_isolado("teste.mascaramento.formatter")
    logger.info("login com password=%s", "senha-que-vaza-1")
    logger.warning("headers=%r", {"Authorization": "Bearer token-que-vaza-2"})
    try:
        raise RuntimeError("falhou: client_secret=segredo-que-vaza-3 access_token=tok-que-vaza-4")
    except RuntimeError:
        logger.exception("erro inesperado")

    texto = saida.getvalue()
    for vazamento in (
        "senha-que-vaza-1",
        "token-que-vaza-2",
        "segredo-que-vaza-3",
        "tok-que-vaza-4",
    ):
        assert vazamento not in texto
    assert "password=***" in texto
    assert "Traceback" in texto


@pytest.mark.parametrize(
    ("linha", "segredo"),
    [
        ("login password=vaza-password-01", "vaza-password-01"),
        ("login senha=vaza-senha-02", "vaza-senha-02"),
        ('{"client_secret": "vaza-client-secret-03"}', "vaza-client-secret-03"),
        ("token=vaza-token-04", "vaza-token-04"),
        ('{"access_token": "vaza-access-token-05"}', "vaza-access-token-05"),
        ("Authorization: vaza-authorization-06", "vaza-authorization-06"),
        ("header Bearer vaza-bearer-000007", "vaza-bearer-000007"),
    ],
    ids=["password", "senha", "client_secret", "token", "access_token", "Authorization", "Bearer"],
)
def test_nenhum_termo_sensivel_sai_no_log(linha, segredo):
    logger, saida = _logger_isolado("teste.mascaramento.termos")
    logger.info(linha)
    texto = saida.getvalue()
    assert segredo not in texto
    assert "***" in texto


def test_setup_logging_instala_o_formatter_mascarado(monkeypatch):
    raiz = logging.getLogger()
    monkeypatch.setattr(raiz, "handlers", list(raiz.handlers))
    monkeypatch.setattr(raiz, "level", raiz.level)
    monkeypatch.setattr(logging_config, "_configurado", False)

    setup_logging("INFO")
    assert any(isinstance(h.formatter, FormatterMascarado) for h in raiz.handlers)


def test_logger_do_connector_mascara_pela_chave_sem_segredo_registrado(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NOME):
        logging.getLogger(LOGGER_NOME).warning(
            "descuido: client_secret=nao-registrado-789 Authorization: Bearer nao-registrado-abc"
        )
    assert "nao-registrado-789" not in caplog.text
    assert "nao-registrado-abc" not in caplog.text
    assert "client_secret=***" in caplog.text
