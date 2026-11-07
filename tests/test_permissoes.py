import secrets
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.api.autorizacao import AdminDep, exigir_modulo
from app.core.config import Settings
from app.core.tokens import emitir_token_acesso
from app.database.models import MODULOS_SISTEMA, PermissaoModulo
from app.main import create_app
from app.services.autorizacao import (
    Modulo,
    PermissaoInvalidaError,
    conceder_permissao,
    permissoes_efetivas,
    revogar_permissao,
    tem_permissao,
    validar_modulo,
)
from app.services.usuarios import definir_ativo
from tests.conftest import app_com_sessao, token_para

integration = pytest.mark.integration
RAIZ = Path(__file__).resolve().parent.parent

DASHBOARD = ["/api/v1/dashboard/resumo", "/api/v1/empresas"]
TRANSFERENCIAS = ["/api/v1/transferencias", "/api/v1/transferencias/1"]
PROTEGIDAS = DASHBOARD + TRANSFERENCIAS + ["/api/v1/auth/me", "/api/v1/auth/permissions"]
PERMISSIONS = "/api/v1/auth/permissions"


def test_enum_de_modulos_igual_ao_check_do_banco():
    assert tuple(Modulo) == MODULOS_SISTEMA


@pytest.mark.parametrize("valor", ["dashboard", "ADMIN", "", "RELATORIOS"])
def test_modulo_desconhecido_e_rejeitado(valor):
    with pytest.raises(PermissaoInvalidaError):
        validar_modulo(valor)


def test_health_live_continua_publico(client):
    resposta = client.get("/health/live")
    assert resposta.status_code == 200
    assert client.get("/health").status_code == 200


def test_login_continua_publico_no_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "security" not in paths["/api/v1/auth/login"]["post"]
    assert "security" not in paths["/health/live"]["get"]
    assert "security" not in paths["/health/ready"]["get"]


def test_swagger_documenta_bearer_401_e_403_nas_rotas_de_negocio(client):
    paths = client.get("/openapi.json").json()["paths"]
    for rota in [
        "/api/v1/dashboard/resumo",
        "/api/v1/empresas",
        "/api/v1/transferencias",
        "/api/v1/transferencias/{id}",
    ]:
        operacao = paths[rota]["get"]
        assert operacao["security"] == [{"BearerJWT": []}], rota
        assert {"401", "403"} <= set(operacao["responses"]), rota
    assert paths[PERMISSIONS]["get"]["security"] == [{"BearerJWT": []}]


@pytest.mark.parametrize("rota", PROTEGIDAS)
def test_sem_token_responde_401(client, rota):
    resposta = client.get(rota)
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Não autenticado."}
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("rota", PROTEGIDAS)
@pytest.mark.parametrize(
    "cabecalho",
    [
        "Bearer lixo",
        "Bearer a.b.c",
        "Basic bWFyaWE6c2VuaGE=",
        "Bearer "
        + emitir_token_acesso(
            usuario_id=1,
            password_changed_at=None,
            segredo=secrets.token_urlsafe(48),
            expira_minutos=5,
        ),
    ],
)
def test_token_invalido_responde_401(client, rota, cabecalho):
    resposta = client.get(rota, headers={"Authorization": cabecalho})
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Não autenticado."}


def test_401_nao_depende_da_ordem_de_validacao(client):
    assert client.get("/api/v1/transferencias/abc").status_code == 401


@pytest.fixture
def app_db(db):
    app = app_com_sessao(db)
    yield app
    app.dependency_overrides.clear()


def _cliente(app, usuario) -> TestClient:
    return TestClient(app, headers=token_para(app, usuario))


def _linhas(db, usuario) -> dict[str, bool]:
    return {
        p.module: p.can_view
        for p in db.scalars(select(PermissaoModulo).where(PermissaoModulo.user_id == usuario.id))
    }


@integration
def test_admin_nasce_com_administracao_e_dashboard(db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    assert _linhas(db, admin) == {"ADMINISTRACAO": True, "DASHBOARD": True}
    assert permissoes_efetivas(db, admin) == {Modulo.ADMINISTRACAO, Modulo.DASHBOARD}


@integration
def test_operador_nasce_sem_permissao(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    assert _linhas(db, operador) == {}
    assert permissoes_efetivas(db, operador) == frozenset()


@integration
def test_administracao_nunca_e_atribuida_a_operador(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    with pytest.raises(PermissaoInvalidaError):
        conceder_permissao(db, operador, "ADMINISTRACAO")
    assert _linhas(db, operador) == {}


@integration
def test_linha_de_administracao_inserida_por_sql_nao_libera_operador(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    db.execute(
        text(
            "INSERT INTO user_module_permissions (user_id, module, can_view)"
            " VALUES (:id, 'ADMINISTRACAO', true)"
        ),
        {"id": operador.id},
    )
    assert Modulo.ADMINISTRACAO not in permissoes_efetivas(db, operador)
    assert not tem_permissao(db, operador, "ADMINISTRACAO")


@integration
def test_admin_sempre_possui_administracao(db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    with pytest.raises(PermissaoInvalidaError):
        revogar_permissao(db, admin, "ADMINISTRACAO")

    db.execute(text("DELETE FROM user_module_permissions WHERE user_id = :id"), {"id": admin.id})
    assert Modulo.ADMINISTRACAO in permissoes_efetivas(db, admin)


@integration
def test_admin_nao_e_superusuario_dos_modulos_de_negocio(db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    assert not tem_permissao(db, admin, "TRANSFERENCIAS")
    conceder_permissao(db, admin, "TRANSFERENCIAS")
    assert tem_permissao(db, admin, "TRANSFERENCIAS")


@integration
def test_conceder_duas_vezes_nao_duplica(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    conceder_permissao(db, operador, "DASHBOARD")
    conceder_permissao(db, operador, "DASHBOARD")
    assert _linhas(db, operador) == {"DASHBOARD": True}


@integration
def test_revogar_e_conceder_de_novo(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    revogar_permissao(db, operador, "DASHBOARD")
    assert _linhas(db, operador) == {"DASHBOARD": False}
    assert permissoes_efetivas(db, operador) == frozenset()

    conceder_permissao(db, operador, "DASHBOARD")
    assert _linhas(db, operador) == {"DASHBOARD": True}


@integration
def test_revogar_modulo_sem_linha_nao_falha(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    revogar_permissao(db, operador, "VENDAS")
    assert _linhas(db, operador) == {}


@integration
def test_can_view_false_nao_libera(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    db.add(PermissaoModulo(user_id=operador.id, module="DASHBOARD"))
    db.flush()
    assert _linhas(db, operador) == {"DASHBOARD": False}
    assert not tem_permissao(db, operador, "DASHBOARD")


@integration
def test_usuario_inativo_nao_tem_permissao(db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    definir_ativo(db, admin, False)
    assert permissoes_efetivas(db, admin) == frozenset()


def _viola(db, constraint: str, sql: str, **params) -> None:
    with pytest.raises(IntegrityError) as erro:
        with db.begin_nested():
            db.execute(text(sql), params)
    assert erro.value.orig.diag.constraint_name == constraint


_INSERT = "INSERT INTO user_module_permissions (user_id, module) VALUES (:user_id, :module)"


@integration
def test_banco_rejeita_permissao_duplicada(db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    _viola(
        db,
        "uq_user_module_permissions_user_module",
        _INSERT,
        user_id=operador.id,
        module="DASHBOARD",
    )


@integration
@pytest.mark.parametrize("modulo", ["dashboard", "RELATORIOS", ""])
def test_banco_rejeita_modulo_invalido(db, criar_usuario_teste, modulo):
    operador = criar_usuario_teste("joao", "OPERADOR")
    _viola(db, "ck_user_module_permissions_module", _INSERT, user_id=operador.id, module=modulo)


@integration
def test_banco_rejeita_usuario_inexistente(db):
    _viola(
        db,
        "user_module_permissions_user_id_fkey",
        _INSERT,
        user_id=999_999_999,
        module="DASHBOARD",
    )


@integration
def test_permissoes_somem_com_o_usuario(db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    id_ = admin.id
    db.delete(admin)
    db.flush()
    restantes = db.scalar(
        text("SELECT count(*) FROM user_module_permissions WHERE user_id = :id"), {"id": id_}
    )
    assert restantes == 0


@integration
def test_schema_user_module_permissions_no_banco(db):
    constraints = set(
        db.scalars(
            text(
                "SELECT conname FROM pg_constraint"
                " WHERE conrelid = 'user_module_permissions'::regclass"
            )
        )
    )
    assert {
        "user_module_permissions_pkey",
        "user_module_permissions_user_id_fkey",
        "uq_user_module_permissions_user_module",
        "ck_user_module_permissions_module",
    } <= constraints
    padrao = db.scalar(
        text(
            "SELECT column_default FROM information_schema.columns"
            " WHERE table_name = 'user_module_permissions' AND column_name = 'can_view'"
        )
    )
    assert padrao == "false"


def test_migration_nao_concede_permissoes():
    fonte = (RAIZ / "migrations" / "versions" / "0004_user_module_permissions.py").read_text(
        encoding="utf-8"
    )
    for proibido in ("insert", "bulk_insert", "op.execute"):
        assert proibido not in fonte.lower(), proibido


@integration
@pytest.mark.parametrize("rota", DASHBOARD + TRANSFERENCIAS)
def test_operador_sem_permissao_recebe_403(app_db, criar_usuario_teste, rota):
    operador = criar_usuario_teste("joao", "OPERADOR")
    resposta = _cliente(app_db, operador).get(rota)
    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "Sem permissão para acessar este recurso."}


@integration
def test_operador_com_dashboard_acessa_dashboard_e_nao_transferencias(app_db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    cliente = _cliente(app_db, operador)
    for rota in DASHBOARD:
        assert cliente.get(rota).status_code == 200, rota
    for rota in TRANSFERENCIAS:
        assert cliente.get(rota).status_code == 403, rota


@integration
def test_operador_com_transferencias_acessa_transferencias_e_nao_dashboard(
    app_db, criar_usuario_teste
):
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=["TRANSFERENCIAS"])
    cliente = _cliente(app_db, operador)
    assert cliente.get("/api/v1/transferencias").status_code == 200

    assert cliente.get("/api/v1/transferencias/999999999").status_code == 404
    for rota in DASHBOARD:
        assert cliente.get(rota).status_code == 403, rota


@integration
def test_permissao_revogada_vale_na_hora(app_db, db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    cliente = _cliente(app_db, operador)
    assert cliente.get("/api/v1/empresas").status_code == 200

    revogar_permissao(db, operador, "DASHBOARD")
    assert cliente.get("/api/v1/empresas").status_code == 403


@integration
def test_admin_acessa_modulos_permitidos(app_db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    cliente = _cliente(app_db, admin)
    for rota in DASHBOARD:
        assert cliente.get(rota).status_code == 200, rota

    assert cliente.get("/api/v1/transferencias").status_code == 403


@integration
def test_usuario_desativado_recebe_401_e_nao_403(app_db, db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    cliente = _cliente(app_db, operador)
    definir_ativo(db, operador, False)
    assert cliente.get("/api/v1/empresas").status_code == 401


@integration
def test_papel_enviado_pelo_cliente_e_ignorado(app_db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    cliente = _cliente(app_db, operador)
    resposta = cliente.get(
        "/api/v1/empresas",
        params={"role": "ADMIN", "modulos": "DASHBOARD"},
        headers={"X-Role": "ADMIN", "X-Permissions": "DASHBOARD"},
    )
    assert resposta.status_code == 403


@pytest.fixture
def app_com_rota_admin(app_db):
    rota = APIRouter(dependencies=[Depends(exigir_modulo(Modulo.ADMINISTRACAO))])

    @rota.get("/api/v1/admin/teste")
    def _admin(usuario: AdminDep) -> dict[str, int]:
        return {"id": usuario.id}

    app_db.include_router(rota)
    return app_db


@integration
def test_admin_acessa_rota_administrativa(app_com_rota_admin, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    resposta = _cliente(app_com_rota_admin, admin).get("/api/v1/admin/teste")
    assert resposta.status_code == 200
    assert resposta.json() == {"id": admin.id}


@integration
def test_operador_com_todos_os_modulos_nao_acessa_rota_administrativa(
    app_com_rota_admin, criar_usuario_teste
):
    todos = [m for m in Modulo if m is not Modulo.ADMINISTRACAO]
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=todos)
    resposta = _cliente(app_com_rota_admin, operador).get("/api/v1/admin/teste")
    assert resposta.status_code == 403


def test_rota_administrativa_sem_token_responde_401():
    app = create_app(Settings(_env_file=None, app_env="test"))
    rota = APIRouter()

    @rota.get("/api/v1/admin/teste")
    def _admin(usuario: AdminDep) -> None:
        return None

    app.include_router(rota)
    assert TestClient(app).get("/api/v1/admin/teste").status_code == 401


@integration
def test_permissions_do_admin(app_db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN", modulos=["ALERTAS"])
    resposta = _cliente(app_db, admin).get(PERMISSIONS)
    assert resposta.status_code == 200

    assert resposta.json() == {
        "modulos": ["DASHBOARD", "ALERTAS", "ADMINISTRACAO"],
        "abas": None,
        "tela_inicial": None,
    }


@integration
def test_permissions_do_operador(app_db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR", modulos=["TRANSFERENCIAS", "DASHBOARD"])
    resposta = _cliente(app_db, operador).get(PERMISSIONS)
    assert resposta.json() == {
        "modulos": ["DASHBOARD", "TRANSFERENCIAS"],
        "abas": None,
        "tela_inicial": None,
    }


@integration
def test_permissions_sem_modulos_responde_lista_vazia(app_db, criar_usuario_teste):
    operador = criar_usuario_teste("joao", "OPERADOR")
    resposta = _cliente(app_db, operador).get(PERMISSIONS)
    assert resposta.status_code == 200
    assert resposta.json() == {"modulos": [], "abas": None, "tela_inicial": None}


@integration
def test_permissions_nao_expoe_dados_sensiveis(app_db, criar_usuario_teste):
    admin = criar_usuario_teste("ana", "ADMIN")
    resposta = _cliente(app_db, admin).get(PERMISSIONS)
    assert set(resposta.json()) == {"modulos", "abas", "tela_inicial"}
    for proibido in ("argon2", "password", "hash", "ana", "user_id", "can_view"):
        assert proibido not in resposta.text.lower(), proibido


def test_lista_de_modulos_tem_uma_fonte_so():
    from typing import get_args

    from app.api.schemas_admin import ModuloNome
    from app.database.models import MODULOS_SISTEMA
    from app.dominio.modulos import Modulo

    valores = tuple(m.value for m in Modulo)
    assert MODULOS_SISTEMA == valores
    assert get_args(ModuloNome) == valores
