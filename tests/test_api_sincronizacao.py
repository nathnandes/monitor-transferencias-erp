import pytest
from fastapi.testclient import TestClient

from app.database.models import IntegracaoErro
from app.sync.comum import finalizar_execucao_isolada, iniciar_execucao
from tests.conftest import app_com_sessao, token_para
from tests.sync_fakes import fabrica_de

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_api(db_vazio, criar_usuario_teste):
    db = db_vazio
    admin = criar_usuario_teste("admin.sync", "ADMIN")
    app = app_com_sessao(db)
    yield TestClient(app, headers=token_para(app, admin))
    app.dependency_overrides.clear()


def test_sem_token_401(client):
    assert client.post("/api/v1/sync/stock").status_code == 401
    assert client.get("/api/v1/sync/status").status_code == 401


def test_operador_nao_pode_pedir_nem_ver(db, criar_usuario_teste):
    operador = criar_usuario_teste("op.sync", "OPERADOR", modulos=["DASHBOARD", "ESTOQUE"])
    app = app_com_sessao(db)
    cliente = TestClient(app, headers=token_para(app, operador))

    assert cliente.post("/api/v1/sync/stock").status_code == 403
    assert cliente.post("/api/v1/sync/companies").status_code == 403
    assert cliente.get("/api/v1/sync/status").status_code == 403


def test_pedido_fica_pendente_e_pedir_de_novo_devolve_o_mesmo(admin_api):
    primeiro = admin_api.post("/api/v1/sync/stock")
    segundo = admin_api.post("/api/v1/sync/stock")
    empresas = admin_api.post("/api/v1/sync/companies")
    completa = admin_api.post("/api/v1/sync/stock/full")

    assert primeiro.status_code == 202
    corpo = primeiro.json()
    assert (corpo["tipo"], corpo["status"], corpo["solicitado_por"]) == (
        "estoque",
        "PENDENTE",
        "admin.sync",
    )
    assert segundo.json()["id"] == corpo["id"]
    assert empresas.json()["tipo"] == "empresas"
    assert empresas.json()["id"] != corpo["id"]
    assert completa.json()["tipo"] == "estoque_completo"

    status = admin_api.get("/api/v1/sync/status").json()
    assert {p["tipo"] for p in status["pendentes"]} == {
        "estoque",
        "empresas",
        "estoque_completo",
    }


def test_status_mostra_ultima_execucao_por_empresa_e_erros(admin_api, db):
    fabrica = fabrica_de(db)
    pai = iniciar_execucao(fabrica, "estoque")
    finalizar_execucao_isolada(
        fabrica,
        pai,
        "parcial",
        mensagem="empresa 3: 403",
        empresas_processadas=1,
        paginas_processadas=2,
        registros_consultados=150,
        registros_criados=100,
        registros_atualizados=50,
    )
    db.add(
        IntegracaoErro(
            sincronizacao_id=pai,
            id_erp_empresa="3",
            endpoint="/erpcore-service/produtos_saldo_estoque_empresa",
            status_http=403,
            tipo_erro="ErpApiAcessoNegadoError",
            mensagem="resposta HTTP de erro | status=403",
        )
    )
    db.flush()

    status = admin_api.get("/api/v1/sync/status").json()

    estoque = status["estoque"]
    assert estoque["id"] == pai
    assert (estoque["status"], estoque["registros_recebidos"], estoque["registros_gravados"]) == (
        "parcial",
        150,
        150,
    )
    assert estoque["paginas_processadas"] == 2
    erro = next(e for e in status["erros_recentes"] if e["sincronizacao_id"] == pai)
    assert (erro["status_http"], erro["id_erp_empresa"]) == (403, "3")
    assert set(status["resumo_estoque"]) == {
        "linhas_ativas",
        "linhas_inativas",
        "produtos_consolidados",
        "consolidado_atualizado_em",
    }


def test_pedido_de_movimentos_de_estoque(admin_api):
    resposta = admin_api.post("/api/v1/sync/stock-movements")

    assert resposta.status_code == 202
    assert (resposta.json()["tipo"], resposta.json()["status"]) == (
        "movimentos_estoque",
        "PENDENTE",
    )
