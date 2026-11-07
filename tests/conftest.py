import os
import secrets
from collections.abc import Callable, Iterator

from dotenv import dotenv_values

os.environ.setdefault("TEST_DATABASE_URL", dotenv_values(".env").get("TEST_DATABASE_URL") or "")
if os.environ["TEST_DATABASE_URL"]:
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import create_app
from tests.bloqueio_rede import bloquear_rede_externa


@pytest.fixture(autouse=True, scope="session")
def _sem_rede_externa() -> Iterator[None]:
    with bloquear_rede_externa():
        yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:

    eng = create_engine(
        get_settings().sqlalchemy_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        with eng.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except SQLAlchemyError:
        pytest.skip("PostgreSQL indisponivel — rode: docker compose up -d db")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    conexao = engine.connect()
    transacao = conexao.begin()

    sessao = Session(bind=conexao, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield sessao
    finally:
        sessao.close()
        transacao.rollback()
        conexao.close()


def esvaziar_dados(db: Session) -> None:
    from sqlalchemy import delete

    from app.database.models import (
        Alerta,
        Atividade,
        Empresa,
        Evento,
        Log,
        Sincronizacao,
        Transferencia,
    )

    db.execute(
        text(
            "TRUNCATE estoque_consolidado, estoque_empresa_local_lote, integracao_erros,"
            " solicitacoes_sincronizacao, precos_produto_empresa, produtos,"
            " vendas_itens, vendas, vendas_dias, vendas_titulos, devolucoes, vendedores,"
            " movimentos_estoque, movimentos_estoque_dias, parametros_avulsas,"
            " limites_pendencia, modelos_mensagem, metas_avisos, metas_vendas, parametros_metas,"
            " parametros_estoque_baixo, estoque_baixo_avisados,"
            " anomalias_transferencias, anomalias_execucoes"
        )
    )

    for model in (Alerta, Atividade, Evento, Sincronizacao, Log, Transferencia, Empresa):
        db.execute(delete(model))


@pytest.fixture
def db_vazio(db: Session) -> Session:
    esvaziar_dados(db)
    return db


@pytest.fixture
def api_db(db: Session) -> Session:
    from app.database.simulacao import aplicar_seed

    esvaziar_dados(db)
    aplicar_seed(db)
    return db


def senha_aleatoria() -> str:
    return secrets.token_urlsafe(16) + "Aa1"


@pytest.fixture
def criar_usuario_teste(db: Session) -> Callable[..., object]:
    from app.services.autorizacao import conceder_permissao
    from app.services.usuarios import criar_usuario

    def _criar(username: str, role: str, *, modulos=(), senha: str | None = None):
        usuario = criar_usuario(
            db,
            username=username,
            nome_exibicao=username.title(),
            senha=senha or senha_aleatoria(),
            role=role,
        )
        for modulo in modulos:
            conceder_permissao(db, usuario, modulo)
        return usuario

    return _criar


def token_para(app, usuario) -> dict[str, str]:
    from app.core.tokens import emitir_token_acesso

    token = emitir_token_acesso(
        usuario_id=usuario.id,
        password_changed_at=usuario.password_changed_at,
        segredo=app.state.auth.segredo,
        expira_minutos=5,
    )
    return {"Authorization": f"Bearer {token}"}


def app_com_sessao(sessao: Session):
    from app.database.session import get_session, get_session_leitura

    app = create_app()
    app.dependency_overrides[get_session] = lambda: sessao
    app.dependency_overrides[get_session_leitura] = lambda: sessao
    return app


@pytest.fixture
def api(api_db: Session, criar_usuario_teste) -> Iterator[TestClient]:
    admin = criar_usuario_teste("admin.teste", "ADMIN", modulos=["TRANSFERENCIAS"])
    app = app_com_sessao(api_db)
    yield TestClient(app, headers=token_para(app, admin))
    app.dependency_overrides.clear()


@pytest.fixture
def client_autorizado() -> Iterator[TestClient]:
    from app.api.autenticacao import get_usuario_autenticado
    from app.api.autorizacao import get_permissoes
    from app.database.models import Usuario
    from app.services.autorizacao import Modulo

    app = create_app()
    app.dependency_overrides[get_usuario_autenticado] = lambda: Usuario(
        id=0, username="stub", role="ADMIN", ativo=True
    )
    app.dependency_overrides[get_permissoes] = lambda: frozenset(Modulo)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def contar_queries(engine: Engine, api_db: Session):
    from contextlib import contextmanager

    from sqlalchemy import event

    @contextmanager
    def _contar():
        api_db.expunge_all()
        comandos: list[str] = []

        def _registrar(conn, cursor, statement, *args):
            ignorar = ("FROM users", "user_module_permissions", "SAVEPOINT")
            if not any(t in statement for t in ignorar):
                comandos.append(statement)

        event.listen(engine, "before_cursor_execute", _registrar)
        try:
            yield comandos
        finally:
            event.remove(engine, "before_cursor_execute", _registrar)

    return _contar
