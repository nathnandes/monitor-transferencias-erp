import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database.session import get_session
from app.main import create_app


def test_live_responde_sem_banco(client):
    resposta = client.get("/health/live")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert corpo["app"] == "erp-automation"


def test_alias_health_continua_funcionando(client):
    assert client.get("/health").json() == client.get("/health/live").json()


def test_ready_responde_503_com_banco_fora():
    class SessaoQuebrada:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", None, Exception("conexao recusada"))

    app = create_app()
    app.dependency_overrides[get_session] = lambda: SessaoQuebrada()
    resposta = TestClient(app).get("/health/ready")

    assert resposta.status_code == 503
    assert resposta.json() == {"status": "indisponivel", "database": "erro"}


@pytest.mark.integration
def test_ready_responde_200_com_banco_no_ar(engine, client):

    resposta = client.get("/health/ready")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "database": "ok"}


def test_live_nao_abre_sessao_de_banco(monkeypatch, client):
    from app.database import session

    def _proibido():
        raise AssertionError("liveness nao pode abrir sessao de banco")

    monkeypatch.setattr(session, "SessionLocal", _proibido)

    assert client.get("/health/live").status_code == 200


def test_rotas_usam_as_settings_passadas_para_a_app():
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(_env_file=None, app_env="test", app_name="App Injetada")
    corpo = TestClient(create_app(settings)).get("/health/live").json()

    assert corpo["app"] == "App Injetada"
