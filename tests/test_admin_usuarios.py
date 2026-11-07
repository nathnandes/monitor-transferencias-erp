import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.seguranca import verificar_senha
from app.database.models import (
    ORIGENS_AUDITORIA,
    TIPOS_EVENTO_AUDITORIA,
    EventoAuditoriaUsuario,
    Usuario,
)
from app.scripts import create_admin
from app.services import admin_usuarios as service
from app.services.auditoria import (
    CHAVES_DETALHES,
    OrigemAuditoria,
    TipoEventoAuditoria,
    eventos_do_usuario,
    registrar_evento,
)
from tests.conftest import app_com_sessao, senha_aleatoria, token_para

integration = pytest.mark.integration

BASE = "/api/v1/admin/users"
ROTAS = [
    ("get", BASE),
    ("post", BASE),
    ("get", f"{BASE}/1"),
    ("patch", f"{BASE}/1"),
    ("post", f"{BASE}/1/reset-password"),
    ("post", f"{BASE}/1/activate"),
    ("post", f"{BASE}/1/deactivate"),
    ("get", f"{BASE}/1/permissions"),
    ("put", f"{BASE}/1/permissions"),
]
CORPOS = {
    "post": {"password_temporaria": "x"},
    "patch": {"nome_exibicao": "x"},
    "put": {"modulos": []},
}
SENSIVEIS = ("password_hash", "$argon2", "eyJ")


def _chamar(cliente: TestClient, metodo: str, rota: str, **kwargs):
    if metodo in CORPOS and "json" not in kwargs:
        kwargs["json"] = CORPOS[metodo]
    return cliente.request(metodo.upper(), rota, **kwargs)


def test_enums_de_auditoria_iguais_aos_checks_do_banco():
    assert tuple(TipoEventoAuditoria) == TIPOS_EVENTO_AUDITORIA
    assert tuple(OrigemAuditoria) == ORIGENS_AUDITORIA


@pytest.mark.parametrize(("metodo", "rota"), ROTAS)
def test_rotas_admin_sem_token_respondem_401(client, metodo, rota):
    resposta = _chamar(client, metodo, rota)
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Não autenticado."}


def test_swagger_documenta_rotas_admin_com_bearer_401_e_403(client):
    paths = client.get("/openapi.json").json()["paths"]
    for metodo, rota in ROTAS:
        rota_doc = rota.replace("/1", "/{id}")
        operacao = paths[rota_doc][metodo]
        assert operacao["security"] == [{"BearerJWT": []}], (metodo, rota_doc)
        assert {"401", "403"} <= set(operacao["responses"]), (metodo, rota_doc)


def test_schemas_de_resposta_nao_tem_campo_de_senha(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for nome in ("UsuarioAdmin", "UsuarioAdminDetalhe", "PaginaUsuarios", "PermissoesAdmin"):
        campos = set(schemas[nome]["properties"])
        suspeitos = {c for c in campos if any(p in c for p in ("password", "senha", "token"))}

        assert suspeitos <= {"must_change_password"}, (nome, suspeitos)


@pytest.mark.parametrize(
    ("metodo", "rota", "corpo"),
    [
        (
            "post",
            BASE,
            {
                "username": "novo",
                "nome_exibicao": "N",
                "role": "OPERADOR",
                "password_temporaria": 123,
                "password_hash": "SEGREDO-ECO",
            },
        ),
        ("patch", f"{BASE}/1", {"password_hash": "SEGREDO-ECO"}),
        ("post", f"{BASE}/1/reset-password", {"password_temporaria": ["SEGREDO-ECO"]}),
    ],
)
def test_422_admin_nao_ecoa_o_valor(client_autorizado, metodo, rota, corpo):
    resposta = _chamar(client_autorizado, metodo, rota, json=corpo)
    assert resposta.status_code == 422
    assert "SEGREDO-ECO" not in resposta.text
    assert all("input" not in erro for erro in resposta.json()["detail"])


def test_auditoria_recusa_chave_ou_valor_sensivel():
    alvo = Usuario(id=1, username="x")
    for detalhes in ({"password": "x"}, {"token": "x"}, {"password_hash": "x"}, {"role": {"a": 1}}):
        with pytest.raises(ValueError):
            registrar_evento(
                None, TipoEventoAuditoria.USUARIO_EDITADO, alvo=alvo, ator=None, detalhes=detalhes
            )


def test_cli_nao_aceita_senha_por_argumento(capsys):
    for argv in (["--password", "x"], ["--senha=x"], ["x"]):
        with pytest.raises(SystemExit) as saida:
            create_admin.main(argv)
        assert saida.value.code == 2
    assert "x" not in capsys.readouterr().out


def test_cli_recusa_terminal_nao_interativo(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert create_admin.main([]) == create_admin.SAIDA_RECUSADO
    assert "terminal interativo" in capsys.readouterr().out


@pytest.fixture
def sem_usuarios(db):
    db.execute(delete(EventoAuditoriaUsuario))
    db.execute(delete(Usuario))
    db.flush()
    return db


@pytest.fixture
def app_db(sem_usuarios):
    app = app_com_sessao(sem_usuarios)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def admin(sem_usuarios, criar_usuario_teste):
    return criar_usuario_teste("chefe", "ADMIN")


@pytest.fixture
def cliente_admin(app_db, admin):
    return TestClient(app_db, headers=token_para(app_db, admin))


def _cliente(app, usuario) -> TestClient:
    return TestClient(app, headers=token_para(app, usuario))


def _criar(cliente, username="joao", role="OPERADOR", senha=None, **extra):
    corpo = {
        "username": username,
        "nome_exibicao": username.title(),
        "password_temporaria": senha or senha_aleatoria(),
        "role": role,
        **extra,
    }
    return cliente.post(BASE, json=corpo)


def _sem_segredo(resposta, *senhas: str) -> None:
    marcadores = SENSIVEIS if resposta.is_success else SENSIVEIS[1:]
    for marcador in (*marcadores, *senhas):
        assert marcador not in resposta.text, marcador


@integration
@pytest.mark.parametrize(("metodo", "rota"), ROTAS)
def test_operador_recebe_403_em_toda_rota_admin(app_db, admin, criar_usuario_teste, metodo, rota):
    operador = criar_usuario_teste(
        "joao", "OPERADOR", modulos=["DASHBOARD", "TRANSFERENCIAS", "ALERTAS"]
    )
    resposta = _chamar(_cliente(app_db, operador), metodo, rota.replace("/1", f"/{admin.id}"))
    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "Sem permissão para acessar este recurso."}


@integration
def test_operador_nao_consegue_se_promover(app_db, criar_usuario_teste, sem_usuarios):
    criar_usuario_teste("chefe", "ADMIN")
    operador = criar_usuario_teste("joao", "OPERADOR")
    cliente = _cliente(app_db, operador)
    resposta = cliente.patch(f"{BASE}/{operador.id}", json={"role": "ADMIN"})
    assert resposta.status_code == 403
    sem_usuarios.refresh(operador)
    assert operador.role == "OPERADOR"


@integration
def test_lista_com_busca_filtros_e_paginacao(cliente_admin, criar_usuario_teste, db):
    criar_usuario_teste("ana.souza", "OPERADOR")
    criar_usuario_teste("bruno", "OPERADOR")
    carla = criar_usuario_teste("carla", "ADMIN")
    carla.nome_exibicao = "Bia Souza"
    inativo = criar_usuario_teste("dora", "OPERADOR")
    inativo.ativo = False
    db.flush()

    tudo = cliente_admin.get(BASE).json()
    assert tudo["total"] == 5
    nomes = [u["username"] for u in tudo["itens"]]
    assert nomes == ["ana.souza", "bruno", "carla", "chefe", "dora"]

    busca = cliente_admin.get(BASE, params={"busca": "SOUZA"}).json()
    assert [u["username"] for u in busca["itens"]] == ["ana.souza", "carla"]

    assert cliente_admin.get(BASE, params={"busca": "%"}).json()["total"] == 0

    assert cliente_admin.get(BASE, params={"ativo": "false"}).json()["itens"][0]["id"] == inativo.id
    assert cliente_admin.get(BASE, params={"ativo": "true"}).json()["total"] == 4
    admins = cliente_admin.get(BASE, params={"role": "ADMIN"}).json()
    assert {u["username"] for u in admins["itens"]} == {"carla", "chefe"}
    assert cliente_admin.get(BASE, params={"role": "ROOT"}).status_code == 422

    pagina = cliente_admin.get(BASE, params={"pagina": 2, "tamanho_pagina": 2}).json()
    assert pagina["total"] == 5 and pagina["total_paginas"] == 3
    assert [u["username"] for u in pagina["itens"]] == ["carla", "chefe"]
    assert cliente_admin.get(BASE, params={"tamanho_pagina": 101}).status_code == 422

    resposta = cliente_admin.get(BASE)
    _sem_segredo(resposta)
    assert set(resposta.json()["itens"][0]) == {
        "id",
        "username",
        "nome_exibicao",
        "role",
        "ativo",
        "must_change_password",
        "sessao_continua",
        "perfil",
        "last_login_at",
        "created_at",
        "updated_at",
    }


@integration
def test_cria_operador_com_senha_temporaria(cliente_admin, db, admin):
    senha = senha_aleatoria()
    resposta = _criar(cliente_admin, " Joao.Silva ", senha=senha, modulos=["TRANSFERENCIAS"])
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["username"] == "joao.silva"
    assert corpo["role"] == "OPERADOR"
    assert corpo["ativo"] is True
    assert corpo["must_change_password"] is True
    assert corpo["modulos"] == ["TRANSFERENCIAS"]
    _sem_segredo(resposta, senha)

    usuario = db.get(Usuario, corpo["id"])
    assert verificar_senha(senha, usuario.password_hash)
    [evento] = eventos_do_usuario(db, usuario.id)
    assert evento.event_type == "USUARIO_CRIADO"
    assert (evento.actor_user_id, evento.actor_username) == (admin.id, "chefe")
    assert evento.detalhes == {
        "role": "OPERADOR",
        "modulos": ["TRANSFERENCIAS"],
        "sessao_continua": False,
        "exigir_troca": True,
    }


@integration
def test_cria_com_senha_facil_sem_exigir_troca(cliente_admin, app_db, db):
    resposta = _criar(cliente_admin, "joao", senha="q1w2", exigir_troca_senha=False)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["must_change_password"] is False
    _sem_segredo(resposta, "q1w2")
    [evento] = eventos_do_usuario(db, resposta.json()["id"])
    assert evento.detalhes["exigir_troca"] is False

    login = TestClient(app_db).post(
        "/api/v1/auth/login", json={"username": "joao", "password": "q1w2"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is False


@integration
def test_usuario_criado_loga_e_deve_trocar_a_senha(cliente_admin, app_db):
    senha = senha_aleatoria()
    _criar(cliente_admin, "joao", senha=senha)
    login = TestClient(app_db).post(
        "/api/v1/auth/login", json={"username": "joao", "password": senha}
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


@integration
def test_cria_admin_com_permissoes_padrao(cliente_admin):
    corpo = _criar(cliente_admin, "maria", role="ADMIN").json()
    assert corpo["modulos"] == ["DASHBOARD", "ADMINISTRACAO"]


@integration
def test_cria_admin_com_lista_explicita_mantem_administracao(cliente_admin):
    corpo = _criar(cliente_admin, "maria", role="ADMIN", modulos=["TRANSFERENCIAS"]).json()
    assert corpo["modulos"] == ["TRANSFERENCIAS", "ADMINISTRACAO"]


@integration
def test_nao_cria_operador_com_administracao(cliente_admin, db):
    resposta = _criar(cliente_admin, "joao", modulos=["DASHBOARD", "ADMINISTRACAO"])
    assert resposta.status_code == 422
    assert "ADMINISTRACAO" in resposta.json()["detail"]
    assert db.scalar(select(Usuario).where(Usuario.username == "joao")) is None


@integration
def test_username_duplicado_sem_diferenca_de_maiusculas(cliente_admin):
    assert _criar(cliente_admin, "joao").status_code == 201
    resposta = _criar(cliente_admin, "JOAO")
    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "Username já cadastrado."}


@integration
@pytest.mark.parametrize("username", ["ab", "com espaco", "acentuação", "x" * 51])
def test_username_invalido(cliente_admin, username):
    assert _criar(cliente_admin, username).status_code == 422


@integration
def test_senha_temporaria_fora_da_politica(cliente_admin, db):
    resposta = _criar(cliente_admin, "joao", senha="a1B")
    assert resposta.status_code == 422
    detalhe = resposta.json()["detail"]
    assert detalhe["mensagem"] == "Senha temporária não atende à política."
    assert "minimo de 4 caracteres" in detalhe["problemas"]
    _sem_segredo(resposta, "a1B")
    assert db.scalar(select(Usuario).where(Usuario.username == "joao")) is None


@integration
def test_criacao_recusa_password_hash(cliente_admin, db):
    resposta = _criar(cliente_admin, "joao", password_hash="$argon2id$v=19$falso")
    assert resposta.status_code == 422
    _sem_segredo(resposta)
    assert db.scalar(select(Usuario).where(Usuario.username == "joao")) is None


@integration
def test_detalhe_e_404(cliente_admin, criar_usuario_teste):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    resposta = cliente_admin.get(f"{BASE}/{joao.id}")
    assert resposta.status_code == 200
    assert resposta.json()["modulos"] == ["DASHBOARD"]
    _sem_segredo(resposta)
    assert cliente_admin.get(f"{BASE}/999999").status_code == 404
    assert cliente_admin.get(f"{BASE}/999999").json() == {"detail": "Usuário não encontrado."}


@integration
def test_patch_nome_e_modulos(cliente_admin, criar_usuario_teste, db, admin):
    joao = criar_usuario_teste("joao", "OPERADOR")
    resposta = cliente_admin.patch(
        f"{BASE}/{joao.id}", json={"nome_exibicao": "  João Silva ", "modulos": ["DASHBOARD"]}
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["nome_exibicao"] == "João Silva"
    assert resposta.json()["modulos"] == ["DASHBOARD"]

    tipos = [e.event_type for e in eventos_do_usuario(db, joao.id)]
    assert tipos == ["USUARIO_EDITADO", "PERMISSOES_ALTERADAS"]


@integration
@pytest.mark.parametrize(
    "corpo",
    [
        {"password_hash": "$argon2id$v=19$falso"},
        {"username": "outro"},
        {"must_change_password": False},
        {"role": "ROOT"},
        {"nome_exibicao": "   "},
        {"modulos": ["ADMINISTRACAO"]},
    ],
)
def test_patch_recusa_campos_e_valores_proibidos(cliente_admin, criar_usuario_teste, db, corpo):
    joao = criar_usuario_teste("joao", "OPERADOR")
    hash_antes = joao.password_hash
    resposta = cliente_admin.patch(f"{BASE}/{joao.id}", json=corpo)
    assert resposta.status_code == 422
    _sem_segredo(resposta)
    db.refresh(joao)
    assert (joao.username, joao.role, joao.password_hash) == ("joao", "OPERADOR", hash_antes)
    assert eventos_do_usuario(db, joao.id) == []


@integration
def test_promover_e_rebaixar(cliente_admin, criar_usuario_teste, db):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["TRANSFERENCIAS"])

    promovido = cliente_admin.patch(f"{BASE}/{joao.id}", json={"role": "ADMIN"}).json()
    assert promovido["role"] == "ADMIN"
    assert promovido["modulos"] == ["DASHBOARD", "TRANSFERENCIAS", "ADMINISTRACAO"]

    assert _cliente(cliente_admin.app, joao).get(BASE).status_code == 200

    rebaixado = cliente_admin.patch(f"{BASE}/{joao.id}", json={"role": "OPERADOR"}).json()
    assert rebaixado["role"] == "OPERADOR"
    assert "ADMINISTRACAO" not in rebaixado["modulos"]
    assert _cliente(cliente_admin.app, joao).get(BASE).status_code == 403

    eventos = eventos_do_usuario(db, joao.id)
    roles = [e.detalhes for e in eventos if e.event_type == "ROLE_ALTERADA"]
    assert roles == [
        {"role_anterior": "OPERADOR", "role_nova": "ADMIN"},
        {"role_anterior": "ADMIN", "role_nova": "OPERADOR"},
    ]
    assert [e.detalhes for e in eventos if e.event_type == "PERMISSOES_ALTERADAS"] == [
        {"modulos_concedidos": ["DASHBOARD", "ADMINISTRACAO"], "modulos_revogados": []},
        {"modulos_concedidos": [], "modulos_revogados": ["ADMINISTRACAO"]},
    ]


@integration
def test_rebaixar_com_administracao_na_mesma_chamada_e_recusado(cliente_admin, criar_usuario_teste):
    maria = criar_usuario_teste("maria", "ADMIN")
    resposta = cliente_admin.patch(
        f"{BASE}/{maria.id}", json={"role": "OPERADOR", "modulos": ["ADMINISTRACAO"]}
    )
    assert resposta.status_code == 422
    assert cliente_admin.get(f"{BASE}/{maria.id}").json()["role"] == "ADMIN"


@integration
@pytest.mark.parametrize("corpo", [{"role": "OPERADOR"}, {"ativo": False}])
def test_admin_nao_altera_o_proprio_papel_nem_se_desativa(
    cliente_admin, criar_usuario_teste, admin, corpo
):
    criar_usuario_teste("maria", "ADMIN")
    resposta = cliente_admin.patch(f"{BASE}/{admin.id}", json=corpo)
    assert resposta.status_code == 409
    assert resposta.json()["detail"] == service.MSG_PROPRIO_USUARIO


@integration
def test_admin_pode_editar_o_proprio_nome_e_modulos(cliente_admin, admin):
    resposta = cliente_admin.patch(
        f"{BASE}/{admin.id}", json={"nome_exibicao": "Chefe", "modulos": ["TRANSFERENCIAS"]}
    )
    assert resposta.status_code == 200
    assert resposta.json()["modulos"] == ["TRANSFERENCIAS", "ADMINISTRACAO"]


@integration
def test_reset_exige_troca_e_invalida_tokens(cliente_admin, criar_usuario_teste, db, app_db):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    joao.must_change_password = False
    db.flush()
    token_antigo = token_para(app_db, joao)
    assert TestClient(app_db, headers=token_antigo).get("/api/v1/auth/me").status_code == 200

    nova = senha_aleatoria()
    resposta = cliente_admin.post(
        f"{BASE}/{joao.id}/reset-password", json={"password_temporaria": nova}
    )
    assert resposta.status_code == 200
    assert resposta.json()["must_change_password"] is True
    _sem_segredo(resposta, nova)

    db.refresh(joao)
    assert verificar_senha(nova, joao.password_hash)
    assert TestClient(app_db, headers=token_antigo).get("/api/v1/auth/me").status_code == 401
    [evento] = eventos_do_usuario(db, joao.id)
    assert (evento.event_type, evento.detalhes) == ("SENHA_REDEFINIDA", {"exigir_troca": True})


@integration
def test_reset_sem_exigir_troca(cliente_admin, criar_usuario_teste, db):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    resposta = cliente_admin.post(
        f"{BASE}/{joao.id}/reset-password",
        json={"password_temporaria": "q1w2", "exigir_troca_senha": False},
    )
    assert resposta.status_code == 200
    assert resposta.json()["must_change_password"] is False
    _sem_segredo(resposta, "q1w2")

    db.refresh(joao)
    assert verificar_senha("q1w2", joao.password_hash)
    [evento] = eventos_do_usuario(db, joao.id)
    assert (evento.event_type, evento.detalhes) == ("SENHA_REDEFINIDA", {"exigir_troca": False})


@integration
def test_reset_com_senha_fraca(cliente_admin, criar_usuario_teste, db):
    joao = criar_usuario_teste("joao", "OPERADOR")
    hash_antes = joao.password_hash
    resposta = cliente_admin.post(
        f"{BASE}/{joao.id}/reset-password", json={"password_temporaria": "a1B"}
    )
    assert resposta.status_code == 422
    assert "minimo de 4 caracteres" in resposta.json()["detail"]["problemas"]
    _sem_segredo(resposta, "a1B")
    db.refresh(joao)
    assert joao.password_hash == hash_antes


@integration
def test_admin_nao_redefine_a_propria_senha(cliente_admin, admin):
    resposta = cliente_admin.post(
        f"{BASE}/{admin.id}/reset-password", json={"password_temporaria": senha_aleatoria()}
    )
    assert resposta.status_code == 409


@integration
def test_desativar_e_ativar(cliente_admin, criar_usuario_teste, db, app_db):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    token = token_para(app_db, joao)

    resposta = cliente_admin.post(f"{BASE}/{joao.id}/deactivate")
    assert resposta.status_code == 200
    assert resposta.json()["ativo"] is False

    assert resposta.json()["modulos"] == ["DASHBOARD"]
    assert TestClient(app_db, headers=token).get("/api/v1/empresas").status_code == 401

    assert cliente_admin.post(f"{BASE}/{joao.id}/deactivate").status_code == 200

    assert cliente_admin.post(f"{BASE}/{joao.id}/activate").json()["ativo"] is True
    assert TestClient(app_db, headers=token).get("/api/v1/auth/me").status_code == 200

    tipos = [e.event_type for e in eventos_do_usuario(db, joao.id)]
    assert tipos == ["USUARIO_DESATIVADO", "USUARIO_ATIVADO"]
    assert cliente_admin.post(f"{BASE}/999999/deactivate").status_code == 404


@integration
def test_unico_admin_nao_se_desativa(cliente_admin, admin, db):
    resposta = cliente_admin.post(f"{BASE}/{admin.id}/deactivate")
    assert resposta.status_code == 409
    assert resposta.json()["detail"] == service.MSG_ULTIMO_ADMIN
    db.refresh(admin)
    assert admin.ativo is True


@integration
def test_admin_desativa_outro_admin_mas_nao_a_si_mesmo(cliente_admin, criar_usuario_teste, admin):
    maria = criar_usuario_teste("maria", "ADMIN")
    assert cliente_admin.post(f"{BASE}/{admin.id}/deactivate").json()["detail"] == (
        service.MSG_PROPRIO_USUARIO
    )
    assert cliente_admin.post(f"{BASE}/{maria.id}/deactivate").status_code == 200


@integration
def test_servico_protege_o_ultimo_admin_sem_ator(sem_usuarios, criar_usuario_teste):
    db = sem_usuarios
    unico = criar_usuario_teste("chefe", "ADMIN")
    with pytest.raises(service.RegraAdministracaoError, match="sem nenhum ADMIN"):
        service.alterar_ativo(db, ator=None, alvo=unico, ativo=False)
    with pytest.raises(service.RegraAdministracaoError, match="sem nenhum ADMIN"):
        service.atualizar_usuario(db, ator=None, alvo=unico, role="OPERADOR")

    outro = criar_usuario_teste("maria", "ADMIN")
    outro.ativo = False
    db.flush()
    with pytest.raises(service.RegraAdministracaoError):
        service.alterar_ativo(db, ator=None, alvo=unico, ativo=False)

    service.alterar_ativo(db, ator=None, alvo=outro, ativo=True)
    service.alterar_ativo(db, ator=None, alvo=unico, ativo=False)
    assert unico.ativo is False
    with pytest.raises(service.RegraAdministracaoError):
        service.alterar_ativo(db, ator=None, alvo=outro, ativo=False)


@integration
def test_get_e_put_permissions(cliente_admin, criar_usuario_teste, db):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    rota = f"{BASE}/{joao.id}/permissions"
    assert cliente_admin.get(rota).json() == {"user_id": joao.id, "modulos": ["DASHBOARD"]}

    resposta = cliente_admin.put(rota, json={"modulos": ["TRANSFERENCIAS", "ALERTAS"]})
    assert resposta.status_code == 200
    assert resposta.json()["modulos"] == ["TRANSFERENCIAS", "ALERTAS"]
    assert _cliente(cliente_admin.app, joao).get("/api/v1/empresas").status_code == 403

    cliente_admin.put(rota, json={"modulos": ["ALERTAS", "TRANSFERENCIAS"]})
    [evento] = eventos_do_usuario(db, joao.id)
    assert evento.detalhes == {
        "modulos_concedidos": ["TRANSFERENCIAS", "ALERTAS"],
        "modulos_revogados": ["DASHBOARD"],
    }


@integration
def test_put_permissions_nao_da_administracao_a_operador(cliente_admin, criar_usuario_teste, db):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])
    rota = f"{BASE}/{joao.id}/permissions"
    resposta = cliente_admin.put(rota, json={"modulos": ["DASHBOARD", "ADMINISTRACAO"]})
    assert resposta.status_code == 422
    assert cliente_admin.put(rota, json={"modulos": ["RELATORIOS"]}).status_code == 422
    assert cliente_admin.get(rota).json()["modulos"] == ["DASHBOARD"]
    assert eventos_do_usuario(db, joao.id) == []


@integration
def test_put_permissions_de_admin_mantem_administracao(cliente_admin, criar_usuario_teste):
    maria = criar_usuario_teste("maria", "ADMIN")
    resposta = cliente_admin.put(f"{BASE}/{maria.id}/permissions", json={"modulos": []})
    assert resposta.json()["modulos"] == ["ADMINISTRACAO"]


@integration
def test_auditoria_completa_sem_dados_sensiveis(cliente_admin, db, admin, caplog):
    senhas = [senha_aleatoria(), senha_aleatoria()]
    with caplog.at_level(logging.INFO):
        joao_id = _criar(cliente_admin, "joao", senha=senhas[0]).json()["id"]
        respostas = [
            cliente_admin.patch(f"{BASE}/{joao_id}", json={"nome_exibicao": "João"}),
            cliente_admin.patch(f"{BASE}/{joao_id}", json={"role": "ADMIN"}),
            cliente_admin.put(f"{BASE}/{joao_id}/permissions", json={"modulos": ["ALERTAS"]}),
            cliente_admin.post(
                f"{BASE}/{joao_id}/reset-password", json={"password_temporaria": senhas[1]}
            ),
            cliente_admin.post(f"{BASE}/{joao_id}/deactivate"),
            cliente_admin.post(f"{BASE}/{joao_id}/activate"),
            cliente_admin.get(f"{BASE}/{joao_id}"),
            cliente_admin.get(BASE),
        ]
    for resposta in respostas:
        assert resposta.status_code == 200, resposta.text
        _sem_segredo(resposta, *senhas)

    eventos = eventos_do_usuario(db, joao_id)
    assert {e.event_type for e in eventos} == set(TIPOS_EVENTO_AUDITORIA)
    for evento in eventos:
        assert evento.actor_user_id == admin.id and evento.actor_username == "chefe"
        assert evento.target_user_id == joao_id and evento.target_username == "joao"
        assert evento.origem == "API"
        assert evento.created_at is not None
        assert set(evento.detalhes) <= CHAVES_DETALHES
        linha = json.dumps(
            {c.name: str(getattr(evento, c.name)) for c in EventoAuditoriaUsuario.__table__.c}
        )
        for marcador in (*SENSIVEIS, *senhas, "password", "senha", "token", "secret"):
            assert marcador not in linha, (evento.event_type, marcador)

    logs = caplog.text
    assert "admin.usuario.criado" in logs
    for marcador in (*SENSIVEIS, *senhas):
        assert marcador not in logs


class _Terminal:
    def __init__(self, username="primeiro.admin", nome="Primeiro Admin", senhas=()):
        self._textos = iter([username, nome])
        self._senhas = iter(senhas)
        self.saida: list[str] = []
        self.perguntas_de_senha = 0

    def ler(self, _prompt: str) -> str:
        return next(self._textos)

    def ler_senha(self, _prompt: str) -> str:
        self.perguntas_de_senha += 1
        return next(self._senhas)

    def escrever(self, texto: str) -> None:
        self.saida.append(texto)

    def executar(self, session) -> int:
        return create_admin.executar(
            session, ler=self.ler, ler_senha=self.ler_senha, escrever=self.escrever
        )


@integration
def test_cli_cria_o_primeiro_admin(sem_usuarios):
    db = sem_usuarios
    senha = senha_aleatoria()
    terminal = _Terminal(username="  Primeiro.Admin ", senhas=[senha, senha])
    assert terminal.executar(db) == create_admin.SAIDA_OK

    admin = db.scalar(select(Usuario).where(Usuario.username == "primeiro.admin"))
    assert admin.role == "ADMIN" and admin.ativo
    assert admin.must_change_password is False
    assert verificar_senha(senha, admin.password_hash)
    [evento] = eventos_do_usuario(db, admin.id)
    assert (evento.event_type, evento.origem, evento.actor_user_id) == (
        "USUARIO_CRIADO",
        "CLI",
        None,
    )
    assert evento.detalhes == {
        "role": "ADMIN",
        "modulos": ["DASHBOARD", "ADMINISTRACAO"],
        "sessao_continua": False,
        "exigir_troca": False,
    }
    assert all(senha not in linha and "$argon2" not in linha for linha in terminal.saida)


@integration
def test_cli_recusa_se_ja_existe_admin_ativo(sem_usuarios, admin):
    terminal = _Terminal(senhas=[])
    assert terminal.executar(sem_usuarios) == create_admin.SAIDA_RECUSADO
    assert terminal.perguntas_de_senha == 0
    assert sem_usuarios.scalar(select(Usuario).where(Usuario.username == "primeiro.admin")) is None


@integration
def test_cli_recusa_username_duplicado(sem_usuarios, criar_usuario_teste):
    antigo = criar_usuario_teste("primeiro.admin", "ADMIN")
    antigo.ativo = False
    sem_usuarios.flush()
    terminal = _Terminal(username="PRIMEIRO.ADMIN", senhas=[])
    assert terminal.executar(sem_usuarios) == create_admin.SAIDA_INVALIDO
    assert terminal.perguntas_de_senha == 0
    assert "ja cadastrado" in terminal.saida[-1]


@integration
@pytest.mark.parametrize(
    ("username", "senhas", "trecho"),
    [
        ("a", [], "Invalido"),
        ("primeiro.admin", ["a1B"], "politica"),
        ("primeiro.admin", ["Aa1" + "x" * 10, "Aa1" + "y" * 10], "nao conferem"),
    ],
)
def test_cli_recusa_dados_invalidos(sem_usuarios, username, senhas, trecho):
    terminal = _Terminal(username=username, senhas=senhas)
    assert terminal.executar(sem_usuarios) == create_admin.SAIDA_INVALIDO
    assert trecho in terminal.saida[-1]
    assert sem_usuarios.scalar(select(Usuario)) is None
    for senha in senhas:
        assert all(senha not in linha for linha in terminal.saida)


@integration
def test_cria_operador_com_sessao_continua(cliente_admin, db):
    resposta = _criar(cliente_admin, "tv.loja", modulos=["DASHBOARD"], sessao_continua=True)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["sessao_continua"] is True
    [evento] = eventos_do_usuario(db, resposta.json()["id"])
    assert evento.detalhes["sessao_continua"] is True


@integration
def test_sessao_continua_nunca_para_admin(cliente_admin, db, criar_usuario_teste):
    resposta = _criar(cliente_admin, "tv.chefe", role="ADMIN", sessao_continua=True)
    assert resposta.status_code == 409
    assert "só para OPERADOR" in resposta.json()["detail"]

    tv = criar_usuario_teste("tv.loja", "OPERADOR")
    tv.sessao_continua = True
    db.flush()

    resposta = cliente_admin.patch(f"{BASE}/{tv.id}", json={"role": "ADMIN"})
    assert resposta.status_code == 409
    db.refresh(tv)
    assert (tv.role, tv.sessao_continua) == ("OPERADOR", True)

    resposta = cliente_admin.patch(
        f"{BASE}/{tv.id}", json={"role": "ADMIN", "sessao_continua": False}
    )
    assert resposta.status_code == 200, resposta.text
    assert (resposta.json()["role"], resposta.json()["sessao_continua"]) == ("ADMIN", False)


@integration
def test_liga_e_desliga_sessao_continua_com_auditoria(cliente_admin, db, criar_usuario_teste):
    joao = criar_usuario_teste("joao", "OPERADOR", modulos=["DASHBOARD"])

    resposta = cliente_admin.patch(f"{BASE}/{joao.id}", json={"sessao_continua": True})
    assert resposta.status_code == 200
    assert resposta.json()["sessao_continua"] is True

    cliente_admin.patch(f"{BASE}/{joao.id}", json={"sessao_continua": True})
    cliente_admin.patch(f"{BASE}/{joao.id}", json={"sessao_continua": False})

    eventos = [e for e in eventos_do_usuario(db, joao.id) if e.event_type == "USUARIO_EDITADO"]
    assert [e.detalhes for e in eventos] == [
        {"campos": ["sessao_continua"], "sessao_continua": True},
        {"campos": ["sessao_continua"], "sessao_continua": False},
    ]


@integration
def test_banco_recusa_admin_com_sessao_continua(db, criar_usuario_teste):
    from sqlalchemy.exc import IntegrityError

    chefe = criar_usuario_teste("chefe2", "ADMIN")
    with pytest.raises(IntegrityError), db.begin_nested():
        chefe.sessao_continua = True
        db.flush()
