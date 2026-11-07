from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database.models import Alerta
from app.rules.motor import avaliar
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration
URL = "/api/v1/alertas"


@pytest.fixture
def alertas_api(api_db, criar_usuario_teste):
    avaliar(api_db, api_db.scalar(select(func.now())))
    operador = criar_usuario_teste("op.alertas", "OPERADOR", modulos=["ALERTAS"])
    app = app_com_sessao(api_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_sem_token_401(client):
    assert client.get(URL).status_code == 401


def test_sem_modulo_alertas_403(api_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.sem.alertas", "OPERADOR", modulos=["DASHBOARD"])
    app = app_com_sessao(api_db)
    cliente = TestClient(app, headers=token_para(app, operador))
    assert cliente.get(URL).status_code == 403
    assert cliente.get(f"{URL}/resumo").status_code == 403


def test_lista_abertos_primeiro_com_empresa_e_transferencia(alertas_api, api_db):
    total = api_db.scalar(select(func.count()).select_from(Alerta))

    corpo = alertas_api.get(URL, params={"tamanho_pagina": 100}).json()

    assert corpo["total"] == total
    assert {a["status"] for a in corpo["itens"]} == {"ABERTO"}
    transferencia = next(a for a in corpo["itens"] if a["regra"] == "transferencia_erro")
    assert transferencia["transferencia"]["id_erp"].startswith("DEMO-")
    assert transferencia["empresa"]["codigo"]
    assert transferencia["aberto_em"].endswith("Z")
    datas = [a["aberto_em"] for a in corpo["itens"]]
    assert datas == sorted(datas, reverse=True)


def test_filtros_por_severidade_status_e_empresa(alertas_api):
    criticos = alertas_api.get(URL, params={"severidade": "CRITICAL"}).json()
    assert criticos["total"] > 0
    assert {a["severidade"] for a in criticos["itens"]} == {"CRITICAL"}

    assert alertas_api.get(URL, params={"status": "RESOLVIDO"}).json()["total"] == 0

    empresa = criticos["itens"][0]["empresa"]["codigo"]
    da_empresa = alertas_api.get(URL, params={"empresa": empresa}).json()
    assert da_empresa["total"] > 0
    assert {a["empresa"]["codigo"] for a in da_empresa["itens"]} == {empresa}


def test_filtro_invalido_422(alertas_api):
    assert alertas_api.get(URL, params={"severidade": "GRAVE"}).status_code == 422
    assert alertas_api.get(URL, params={"status": "aberto"}).status_code == 422


def test_paginacao(alertas_api):
    corpo = alertas_api.get(URL, params={"tamanho_pagina": 2, "pagina": 1}).json()
    assert len(corpo["itens"]) == 2
    assert corpo["total_paginas"] == -(-corpo["total"] // 2)


def test_resumo_conta_abertos_por_severidade(alertas_api, api_db):
    esperado = Counter(
        api_db.scalars(select(Alerta.severidade).where(Alerta.status == "ABERTO")).all()
    )

    corpo = alertas_api.get(f"{URL}/resumo").json()

    assert corpo["abertos"] == sum(esperado.values())
    assert set(corpo["por_severidade"]) == {"INFO", "WARNING", "ERROR", "CRITICAL"}
    for severidade, total in corpo["por_severidade"].items():
        assert total == esperado.get(severidade, 0)
