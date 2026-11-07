from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database.models import Sincronizacao
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration


@pytest.fixture
def cliente(db_vazio, criar_usuario_teste):

    usuario = criar_usuario_teste("sem.modulo", "OPERADOR")
    app = app_com_sessao(db_vazio)
    yield TestClient(app, headers=token_para(app, usuario))
    app.dependency_overrides.clear()


def test_sem_token_e_401(db_vazio):
    app = app_com_sessao(db_vazio)
    assert TestClient(app).get("/api/v1/frescor").status_code == 401


def test_qualquer_usuario_ve_a_situacao_de_cada_tipo(cliente, db_vazio):
    agora = db_vazio.scalar(select(func.now()))
    db_vazio.add(
        Sincronizacao(
            tipo="transferencias",
            inicio=agora - timedelta(minutes=3),
            fim=agora - timedelta(minutes=2),
            status="sucesso",
        )
    )
    db_vazio.flush()

    resposta = cliente.get("/api/v1/frescor")

    assert resposta.status_code == 200
    corpo = resposta.json()
    situacoes = {t["tipo"]: t["situacao"] for t in corpo["tipos"]}
    assert situacoes == {
        "transferencias": "EM_DIA",
        "estoque": "NUNCA",
        "precos": "NUNCA",
        "vendas": "NUNCA",
        "movimentos_estoque": "NUNCA",
    }
    transferencias = next(t for t in corpo["tipos"] if t["tipo"] == "transferencias")
    assert transferencias["ultima_conclusao"] is not None
    assert transferencias["limite_segundos"] == 30 * 60
    assert "gerado_em" in corpo
