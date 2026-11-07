import pytest
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration


def test_conecta_no_banco(engine):
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT 1")).scalar() == 1


def test_tabela_empresas_existe(engine):
    tabelas = inspect(engine).get_table_names()

    assert "empresas" in tabelas, "tabela ausente — rode: alembic upgrade head"


def test_readiness_responde_ok_com_banco_no_ar(engine, client):
    resposta = client.get("/health/ready")

    assert resposta.status_code == 200
    assert resposta.json()["database"] == "ok"
