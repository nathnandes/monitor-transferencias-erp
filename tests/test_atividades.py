from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.database.models import AlertaConfiguracao, AlertaDestino, Atividade, Notificacao
from app.notifications.outbox import processar_pendentes
from app.services import atividades
from app.services import config_alertas as config_service
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

TZ = ZoneInfo("America/Porto_Velho")
SENHA = "Teste#Atividade1"


class EnviadorFalso:
    canal = "telegram"

    def __init__(self) -> None:
        self.envios: list[tuple[str | None, str]] = []

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        self.envios.append((chat_id, texto))


@pytest.fixture
def cfg_db(api_db):
    api_db.execute(delete(AlertaConfiguracao))
    api_db.execute(delete(AlertaDestino))
    api_db.execute(delete(Atividade))
    api_db.add(AlertaDestino(nome="Padrão", chat_id=None))
    api_db.flush()
    return api_db


@pytest.fixture
def cliente(cfg_db):
    app = app_com_sessao(cfg_db)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _padrao(db) -> AlertaDestino:
    return db.scalar(select(AlertaDestino).where(AlertaDestino.chat_id.is_(None)))


def _ligar(db, tipo: str, *destinos: AlertaDestino) -> None:
    config_service.salvar_regra(
        db,
        tipo,
        ativo=True,
        campos=["usuario", "quando", "detalhe"],
        destinos_ids=[d.id for d in destinos],
    )


def _atividades(db, tipo: str) -> list[Atividade]:
    return list(db.scalars(select(Atividade).where(Atividade.tipo == tipo)))


def test_login_e_saida_ficam_no_historico_sem_aviso_por_padrao(
    cfg_db, cliente, criar_usuario_teste
):
    criar_usuario_teste("maria.ativ", "OPERADOR", modulos=["DASHBOARD"], senha=SENHA)
    resposta = cliente.post(
        "/api/v1/auth/login", json={"username": "maria.ativ", "password": SENHA}
    )
    assert resposta.status_code == 200
    token = resposta.json()["access_token"]
    assert (
        cliente.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 204
    )

    [login] = _atividades(cfg_db, "login")
    assert login.resumo == "Maria.Ativ entrou no sistema"
    assert login.usuario_id is not None and login.ip
    assert [a.resumo for a in _atividades(cfg_db, "logout")] == ["Maria.Ativ saiu do sistema"]

    assert cfg_db.scalar(select(func.count()).select_from(Notificacao)) == 0


def test_login_recusado_guarda_o_usuario_digitado(cfg_db, cliente):
    resposta = cliente.post("/api/v1/auth/login", json={"username": "fulano", "password": "errada"})
    assert resposta.status_code == 401
    [recusado] = _atividades(cfg_db, "login_recusado")
    assert recusado.usuario_nome == "fulano" and recusado.usuario_id is None
    assert "senha incorretos" in (recusado.detalhe or "")


def test_atividade_ligada_vai_para_o_telegram_com_o_modelo(cfg_db, cliente, criar_usuario_teste):

    gerente = AlertaDestino(nome="Gerente", chat_id="-100555", severidade_minima="CRITICAL")
    cfg_db.add(gerente)
    cfg_db.flush()
    _ligar(cfg_db, "login", gerente)
    criar_usuario_teste("joao.ativ", "OPERADOR", modulos=["DASHBOARD"], senha=SENHA)

    cliente.post("/api/v1/auth/login", json={"username": "joao.ativ", "password": SENHA})

    [n] = cfg_db.scalars(select(Notificacao).where(Notificacao.atividade_id.is_not(None))).all()
    assert n.tipo == "ATIVIDADE" and n.destino_id == gerente.id
    enviador = EnviadorFalso()
    agora = datetime.now(UTC)
    processar_pendentes(cfg_db, enviador, agora, TZ, lote=50)
    [(chat, texto)] = enviador.envios
    assert chat == "-100555"
    assert texto.startswith("👤 Joao.Ativ entrou no sistema")
    assert "Usuário: Joao.Ativ" in texto
    assert n.status == "ENVIADA"


def test_alteracao_de_admin_registra_quem_e_o_que(cfg_db, criar_usuario_teste):
    admin = criar_usuario_teste("admin.ativ", "ADMIN", modulos=["TRANSFERENCIAS"])
    app = app_com_sessao(cfg_db)
    api = TestClient(app, headers=token_para(app, admin))
    resposta = api.put(
        "/api/v1/transferencias/limites", json={"horas_atencao": 12, "horas_critico": 36}
    )
    app.dependency_overrides.clear()

    assert resposta.status_code == 200
    [alteracao] = _atividades(cfg_db, "transferencias_alteradas")
    assert alteracao.resumo == (
        "Admin.Ativ mudou os limites das transferências para 12 h (atenção) e 36 h (crítico)"
    )


def test_alteracao_recusada_nao_registra(cfg_db, criar_usuario_teste):
    admin = criar_usuario_teste("admin.ativ2", "ADMIN", modulos=["TRANSFERENCIAS"])
    app = app_com_sessao(cfg_db)
    api = TestClient(app, headers=token_para(app, admin))
    resposta = api.put(
        "/api/v1/transferencias/limites", json={"horas_atencao": 40, "horas_critico": 20}
    )
    app.dependency_overrides.clear()
    assert resposta.status_code == 422
    assert _atividades(cfg_db, "transferencias_alteradas") == []


def test_historico_filtra_por_tipo_e_usuario(cfg_db, criar_usuario_teste):
    admin = criar_usuario_teste("admin.hist", "ADMIN", modulos=["ADMINISTRACAO"])
    atividades.registrar(cfg_db, "login", "Ana entrou no sistema", usuario_nome="Ana")
    atividades.registrar(cfg_db, "logout", "Ana saiu do sistema", usuario_nome="Ana")
    atividades.registrar(cfg_db, "login", "Bia entrou no sistema", usuario_nome="Bia")
    app = app_com_sessao(cfg_db)
    api = TestClient(app, headers=token_para(app, admin))

    corpo = api.get("/api/v1/admin/atividades", params={"tipo": "login"}).json()
    assert corpo["total"] == 2 and {i["tipo_nome"] for i in corpo["itens"]} == {
        "Entrada no sistema"
    }
    assert "login_recusado" in {t["chave"] for t in corpo["tipos"]}
    corpo = api.get("/api/v1/admin/atividades", params={"usuario": "an"}).json()
    assert [i["resumo"] for i in corpo["itens"]] == ["Ana saiu do sistema", "Ana entrou no sistema"]
    app.dependency_overrides.clear()


def test_historico_exige_admin(cfg_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.hist", "OPERADOR", modulos=["ALERTAS"])
    app = app_com_sessao(cfg_db)
    api = TestClient(app, headers=token_para(app, operador))
    assert api.get("/api/v1/admin/atividades").status_code == 403
    app.dependency_overrides.clear()


def test_tipo_desconhecido_e_erro_de_programacao(cfg_db):
    with pytest.raises(ValueError, match="atividade desconhecida"):
        atividades.registrar(cfg_db, "transferencia_erro", "x")
