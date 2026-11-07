from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.session import get_session_leitura
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("papel", ["ADMIN", "OPERADOR"])
def test_rota_de_consulta_abre_a_sessao_sem_transacao_pendente(
    api_db: Session, criar_usuario_teste, papel: str
) -> None:
    usuario = criar_usuario_teste("pool.teste", papel, modulos=["DASHBOARD"])
    app = app_com_sessao(api_db)
    em_transacao: list[bool] = []

    def espiar_leitura() -> Iterator[Session]:

        em_transacao.append(api_db.in_transaction())
        yield api_db

    app.dependency_overrides[get_session_leitura] = espiar_leitura
    try:
        resposta = TestClient(app, headers=token_para(app, usuario)).get("/api/v1/empresas")
    finally:
        app.dependency_overrides.clear()

    assert resposta.status_code == 200
    assert em_transacao == [False]
