import io
import json
import logging

from app.core.logging_config import FormatterJson, FormatterMascarado
from app.core.requisicao import definir_request_id, restaurar_request_id


def test_resposta_traz_request_id_gerado(client):
    resposta = client.get("/health/live")
    rid = resposta.headers["x-request-id"]
    assert len(rid) == 32 and rid.isalnum()


def test_request_id_valido_recebido_e_reaproveitado(client):
    resposta = client.get("/health/live", headers={"X-Request-ID": "proxy-abc.123"})
    assert resposta.headers["x-request-id"] == "proxy-abc.123"


def test_request_id_invalido_e_trocado(client):
    resposta = client.get("/health/live", headers={"X-Request-ID": "x" * 65})
    assert resposta.headers["x-request-id"] != "x" * 65
    resposta = client.get("/health/live", headers={"X-Request-ID": "a b<script>"})
    assert "<" not in resposta.headers["x-request-id"]


def test_log_por_requisicao_sem_query_string(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.http"):
        client.get("/api/v1/transferencias?numero=SEGREDO-DA-QUERY")
    registros = [r for r in caplog.records if r.name == "app.http"]
    assert len(registros) == 1
    registro = registros[0]
    assert registro.caminho == "/api/v1/transferencias"
    assert registro.status == 401
    assert "SEGREDO-DA-QUERY" not in registro.getMessage()


def test_health_nao_gera_log_de_requisicao(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.http"):
        client.get("/health/live")
    assert not [r for r in caplog.records if r.name == "app.http"]


def _formatar(formatter: logging.Formatter, mensagem: str, **extra) -> str:
    saida = io.StringIO()
    handler = logging.StreamHandler(saida)
    handler.setFormatter(formatter)
    logger = logging.getLogger("teste.observabilidade")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.warning(mensagem, extra=extra)
    finally:
        logger.removeHandler(handler)
    return saida.getvalue().strip()


def test_formato_json_tem_campos_extra_e_request_id():
    token = definir_request_id("req-1")
    try:
        linha = _formatar(FormatterJson(), "oi %s", status=200)
    finally:
        restaurar_request_id(token)
    evento = json.loads(linha)
    assert evento["msg"] == "oi %s"
    assert evento["nivel"] == "WARNING"
    assert evento["request_id"] == "req-1"
    assert evento["status"] == 200


def test_formato_json_mascara_segredo():
    linha = _formatar(FormatterJson(), "falhou password=abc123segredo")
    assert "abc123segredo" not in linha
    json.loads(linha)


def test_formato_texto_acrescenta_request_id():
    token = definir_request_id("req-2")
    try:
        linha = _formatar(FormatterMascarado("%(message)s"), "oi")
    finally:
        restaurar_request_id(token)
    assert linha == "oi [req=req-2]"
