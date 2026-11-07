from typing import get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.schemas_admin import ModuloDePerfil
from app.api.schemas_auth import AbaNome
from app.database.models import EventoAuditoriaUsuario
from app.dominio.abas import MODULOS_DE_PERFIL, Aba
from app.dominio.modulos import Modulo
from tests.conftest import app_com_sessao, token_para

PERFIS = "/api/v1/admin/perfis"

ESTOQUISTA = {
    "nome": "Estoquista",
    "descricao": "Só avulsas e justificativas",
    "modulos": ["ESTOQUE", "ALERTAS"],
    "abas": ["ESTOQUE.AVULSAS", "ESTOQUE.JUSTIFICATIVAS"],
    "tela_inicial": "ESTOQUE.AVULSAS",
}


@pytest.fixture
def app_db(db):
    app = app_com_sessao(db)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def admin(app_db, criar_usuario_teste) -> TestClient:
    usuario = criar_usuario_teste("chefe", "ADMIN")
    return TestClient(app_db, headers=token_para(app_db, usuario))


def test_contrato_tem_as_mesmas_abas_e_modulos_do_dominio():
    assert list(get_args(AbaNome)) == [a.value for a in Aba]
    sem_administracao = [m.value for m in Modulo if m is not Modulo.ADMINISTRACAO]
    assert list(MODULOS_DE_PERFIL) == sem_administracao
    assert list(get_args(ModuloDePerfil)) == sem_administracao


def test_cria_lista_altera_e_exclui(admin):
    r = admin.post(PERFIS, json=ESTOQUISTA)
    assert r.status_code == 201, r.text
    criado = r.json()
    assert criado["modulos"] == ["ESTOQUE", "ALERTAS"]
    assert criado["abas"] == ["ESTOQUE.AVULSAS", "ESTOQUE.JUSTIFICATIVAS"]
    assert criado["usuarios"] == 0

    assert [p["nome"] for p in admin.get(PERFIS).json()] == ["Estoquista"]

    r = admin.put(
        f"{PERFIS}/{criado['id']}",
        json={**ESTOQUISTA, "abas": ["ESTOQUE.SALDOS"], "tela_inicial": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["abas"] == ["ESTOQUE.SALDOS"]

    assert admin.delete(f"{PERFIS}/{criado['id']}").status_code == 204
    assert admin.get(PERFIS).json() == []


@pytest.mark.parametrize(
    ("mudanca", "trecho"),
    [
        ({"abas": ["VENDAS.TV", "ESTOQUE.SALDOS"]}, "precisa do módulo VENDAS"),
        ({"abas": ["ESTOQUE.JUSTIFICATIVAS"]}, "dentro de ESTOQUE.AVULSAS"),
        ({"abas": []}, "ao menos uma aba"),
        (
            {"modulos": ["ESTOQUE", "VENDAS"], "abas": ["ESTOQUE.SALDOS", "VENDAS.TV"]},
            "VENDAS precisa de ao menos uma aba",
        ),
        ({"tela_inicial": "VENDAS"}, "liberada no perfil"),
        ({"tela_inicial": "ESTOQUE.JUSTIFICATIVAS"}, "desconhecida"),
        ({"nome": "   "}, "nome"),
    ],
)
def test_recusa_perfil_incoerente(admin, mudanca, trecho):
    r = admin.post(PERFIS, json={**ESTOQUISTA, **mudanca})
    assert r.status_code == 422
    assert trecho in r.json()["detail"]


def test_perfil_de_vendas_so_de_uma_loja(admin):
    r = admin.post(
        PERFIS,
        json={
            "nome": "Vendas Loja Norte",
            "descricao": None,
            "modulos": ["VENDAS"],
            "abas": ["VENDAS.EMPRESA_2", "VENDAS.TV"],
            "tela_inicial": "VENDAS.EMPRESA_2",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["abas"] == ["VENDAS.TV", "VENDAS.EMPRESA_2"]


def test_administracao_nao_entra_no_perfil(admin):
    r = admin.post(PERFIS, json={**ESTOQUISTA, "modulos": ["ESTOQUE", "ADMINISTRACAO"]})
    assert r.status_code == 422


def test_nome_repetido_e_409(admin):
    assert admin.post(PERFIS, json=ESTOQUISTA).status_code == 201
    r = admin.post(PERFIS, json={**ESTOQUISTA, "nome": "estoquista"})
    assert r.status_code == 409


def test_operador_nao_mexe_em_perfis(app_db, criar_usuario_teste):
    operador = criar_usuario_teste("ana", "OPERADOR", modulos=["ESTOQUE"])
    cliente = TestClient(app_db, headers=token_para(app_db, operador))
    assert cliente.get(PERFIS).status_code == 403
    assert cliente.post(PERFIS, json=ESTOQUISTA).status_code == 403


def test_perfil_define_modulos_abas_e_tela_inicial(app_db, admin, db, criar_usuario_teste):

    operador = criar_usuario_teste("ana", "OPERADOR", modulos=["DASHBOARD", "VENDAS"])
    cliente = TestClient(app_db, headers=token_para(app_db, operador))
    assert cliente.get("/api/v1/auth/permissions").json() == {
        "modulos": ["DASHBOARD", "VENDAS"],
        "abas": None,
        "tela_inicial": None,
    }

    perfil = admin.post(PERFIS, json=ESTOQUISTA).json()
    r = admin.patch(f"/api/v1/admin/users/{operador.id}", json={"perfil_id": perfil["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["perfil"] == {"id": perfil["id"], "nome": "Estoquista"}

    assert r.json()["modulos"] == ["DASHBOARD", "VENDAS"]

    db.expire_all()
    assert cliente.get("/api/v1/auth/permissions").json() == {
        "modulos": ["ESTOQUE", "ALERTAS"],
        "abas": ["ESTOQUE.AVULSAS", "ESTOQUE.JUSTIFICATIVAS"],
        "tela_inicial": "ESTOQUE.AVULSAS",
    }

    assert cliente.get("/api/v1/vendas/resumo").status_code == 403
    assert cliente.get("/api/v1/estoque/resumo").status_code == 200

    assert admin.get(PERFIS).json()[0]["usuarios"] == 1
    assert admin.delete(f"{PERFIS}/{perfil['id']}").status_code == 409

    r = admin.patch(f"/api/v1/admin/users/{operador.id}", json={"perfil_id": None})
    assert r.json()["perfil"] is None
    db.expire_all()
    assert cliente.get("/api/v1/auth/permissions").json()["modulos"] == ["DASHBOARD", "VENDAS"]

    eventos = db.scalars(
        select(EventoAuditoriaUsuario).where(EventoAuditoriaUsuario.target_user_id == operador.id)
    ).all()
    trocas = [e.detalhes for e in eventos if e.detalhes.get("campos") == ["perfil"]]
    assert trocas == [
        {"campos": ["perfil"], "perfil_anterior": "", "perfil_novo": "Estoquista"},
        {"campos": ["perfil"], "perfil_anterior": "Estoquista", "perfil_novo": ""},
    ]


def test_patch_sem_perfil_id_nao_mexe_no_perfil(app_db, admin, db, criar_usuario_teste):
    operador = criar_usuario_teste("ana", "OPERADOR")
    perfil = admin.post(PERFIS, json=ESTOQUISTA).json()
    admin.patch(f"/api/v1/admin/users/{operador.id}", json={"perfil_id": perfil["id"]})
    r = admin.patch(f"/api/v1/admin/users/{operador.id}", json={"nome_exibicao": "Pessoa Exemplo"})
    assert r.json()["perfil"]["nome"] == "Estoquista"


def test_admin_com_perfil_mantem_administracao(app_db, admin, db, criar_usuario_teste):
    outro = criar_usuario_teste("gerente", "ADMIN")
    perfil = admin.post(PERFIS, json=ESTOQUISTA).json()
    admin.patch(f"/api/v1/admin/users/{outro.id}", json={"perfil_id": perfil["id"]})
    db.expire_all()
    cliente = TestClient(app_db, headers=token_para(app_db, outro))
    assert cliente.get("/api/v1/auth/permissions").json()["modulos"] == [
        "ESTOQUE",
        "ALERTAS",
        "ADMINISTRACAO",
    ]


def test_cria_usuario_ja_com_perfil(admin):
    perfil = admin.post(PERFIS, json=ESTOQUISTA).json()
    r = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "bia",
            "nome_exibicao": "Bia",
            "password_temporaria": "1234",
            "role": "OPERADOR",
            "perfil_id": perfil["id"],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["perfil"]["nome"] == "Estoquista"


def test_perfil_inexistente_e_422(admin, criar_usuario_teste):
    operador = criar_usuario_teste("ana", "OPERADOR")
    r = admin.patch(f"/api/v1/admin/users/{operador.id}", json={"perfil_id": 999_999})
    assert r.status_code == 422
