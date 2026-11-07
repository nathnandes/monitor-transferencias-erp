import logging
import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.limite_tentativas import LimitadorTentativas
from app.core.mascaramento import mascarar_texto
from app.core.seguranca import verificar_senha
from app.core.tokens import (
    ConfiguracaoInseguraError,
    TokenInvalidoError,
    emitir_token_acesso,
    problemas_do_segredo,
    resolver_segredo,
    validar_token_acesso,
    versao_da_senha,
)
from app.database.session import get_session
from app.main import create_app
from app.services.usuarios import criar_usuario, definir_ativo

integration = pytest.mark.integration


SEGREDO = secrets.token_urlsafe(48)
SENHA = "SenhaForte123"
NOVA_SENHA = "NovaSenha456"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
TROCA = "/api/v1/auth/change-password"
LOGOUT = "/api/v1/auth/logout"
RENOVAR = "/api/v1/auth/renew"


def _settings(**campos) -> Settings:
    base = {"_env_file": None, "app_env": "test", "jwt_secret": SEGREDO}
    return Settings(**{**base, **campos})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("segredo", ["", "curto", "changeme", "a" * 64, "ab" * 40])
def test_producao_nao_sobe_com_segredo_ausente_ou_fraco(segredo):
    with pytest.raises(ConfiguracaoInseguraError):
        create_app(_settings(app_env="production", jwt_secret=segredo))


def test_producao_sobe_com_segredo_forte():
    app = create_app(_settings(app_env="production"))
    assert app.state.auth.segredo == SEGREDO


def test_erro_de_segredo_fraco_nao_expoe_o_segredo():
    with pytest.raises(ConfiguracaoInseguraError) as erro:
        resolver_segredo(_settings(app_env="production", jwt_secret="segredo-fraco-x"))
    assert "segredo-fraco-x" not in str(erro.value)


def test_desenvolvimento_sem_segredo_usa_chave_aleatoria_por_processo():
    a = create_app(_settings(jwt_secret=""))
    b = create_app(_settings(jwt_secret=""))
    assert a.state.auth.segredo != b.state.auth.segredo
    assert problemas_do_segredo(a.state.auth.segredo) == []


def test_segredo_gerado_pelo_comando_documentado_e_forte():
    assert problemas_do_segredo(secrets.token_urlsafe(48)) == []


def _emitir(**campos) -> str:
    base = {
        "usuario_id": 7,
        "password_changed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "segredo": SEGREDO,
        "expira_minutos": 30,
    }
    return emitir_token_acesso(**{**base, **campos})


def test_token_valido_e_so_com_claims_minimos():
    token = _emitir()
    claims = validar_token_acesso(token, SEGREDO)
    assert claims.usuario_id == 7
    assert claims.versao_senha == versao_da_senha(datetime(2026, 1, 1, tzinfo=UTC))

    bruto = jwt.decode(token, options={"verify_signature": False})

    assert set(bruto) == {"sub", "typ", "iss", "iat", "exp", "pwv", "ses", "jti"}
    assert bruto["ses"] == bruto["iat"]
    assert bruto["exp"] - bruto["iat"] == 30 * 60
    assert jwt.get_unverified_header(token)["alg"] == "HS256"


def test_token_expirado_e_recusado():
    token = _emitir(agora=datetime.now(UTC) - timedelta(minutes=31))
    with pytest.raises(TokenInvalidoError):
        validar_token_acesso(token, SEGREDO)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "nao-e-jwt",
        "a.b.c",
        jwt.encode({"sub": "7", "typ": "access"}, "outra-chave-" + "x" * 40, algorithm="HS256"),
    ],
)
def test_token_invalido_e_recusado(token):
    with pytest.raises(TokenInvalidoError):
        validar_token_acesso(token, SEGREDO)


def test_token_adulterado_e_recusado():
    cabecalho, payload, assinatura = _emitir().split(".")
    outro_payload = _emitir(usuario_id=1).split(".")[1]
    with pytest.raises(TokenInvalidoError):
        validar_token_acesso(f"{cabecalho}.{outro_payload}.{assinatura}", SEGREDO)


def test_token_com_alg_none_e_recusado():
    agora = datetime.now(UTC)
    claims = {
        "sub": "7",
        "typ": "access",
        "iss": "erp-automation",
        "iat": agora,
        "exp": agora + timedelta(minutes=5),
        "pwv": 0,
    }
    token = jwt.encode(claims, None, algorithm="none")
    with pytest.raises(TokenInvalidoError):
        validar_token_acesso(token, SEGREDO)


def test_token_de_outro_tipo_e_recusado():
    agora = datetime.now(UTC)
    claims = {
        "sub": "7",
        "typ": "refresh",
        "iss": "erp-automation",
        "iat": agora,
        "exp": agora + timedelta(minutes=5),
        "pwv": 0,
    }
    with pytest.raises(TokenInvalidoError):
        validar_token_acesso(jwt.encode(claims, SEGREDO, algorithm="HS256"), SEGREDO)


def test_versao_da_senha_e_exata_ao_microssegundo():
    t = datetime(2026, 9, 29, 12, 0, 0, 123456, tzinfo=UTC)
    assert versao_da_senha(t) != versao_da_senha(t + timedelta(microseconds=1))
    assert versao_da_senha(None) == 0


def test_jwt_e_mascarado_nos_logs():
    token = _emitir()
    assert token not in mascarar_texto(f"recebido {token} no cabecalho")


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


def test_limitador_bloqueia_no_limite_e_libera_apos_a_janela():
    relogio = Relogio()
    limitador = LimitadorTentativas(3, 60, relogio=relogio)
    for _ in range(2):
        limitador.registrar_falha("k")
    assert not limitador.bloqueado("k")
    limitador.registrar_falha("k")
    assert limitador.bloqueado("k")
    assert not limitador.bloqueado("outra")

    relogio.agora += 60
    assert not limitador.bloqueado("k")


def test_limitador_sucesso_zera_a_chave():
    limitador = LimitadorTentativas(2, 60, relogio=Relogio())
    limitador.registrar_falha("k")
    limitador.limpar("k")
    limitador.registrar_falha("k")
    assert not limitador.bloqueado("k")


def test_limitador_tem_teto_de_memoria():
    limitador = LimitadorTentativas(1, 60, relogio=Relogio(), max_chaves=10)
    for i in range(100):
        limitador.registrar_falha(i)
    assert len(limitador._falhas) <= 10
    assert limitador.bloqueado(99)


def test_swagger_tem_bearer_nas_rotas_protegidas():
    openapi = TestClient(create_app(_settings())).get("/openapi.json").json()
    esquema = openapi["components"]["securitySchemes"]["BearerJWT"]
    assert esquema == {
        "type": "http",
        "scheme": "bearer",
        "description": "Cole o access_token devolvido por POST /api/v1/auth/login.",
    }
    for rota, metodo in [(ME, "get"), (TROCA, "post"), (LOGOUT, "post")]:
        assert openapi["paths"][rota][metodo]["security"] == [{"BearerJWT": []}], rota
    assert "security" not in openapi["paths"][LOGIN]["post"]

    assert openapi["paths"]["/api/v1/empresas"]["get"]["security"] == [{"BearerJWT": []}]


@pytest.mark.parametrize("rota", [ME, TROCA, LOGOUT, RENOVAR])
def test_rotas_protegidas_sem_token_respondem_401(rota):
    cliente = TestClient(create_app(_settings()))
    resposta = cliente.request("GET" if rota == ME else "POST", rota)
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Não autenticado."}
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "corpo",
    [
        {"username": "maria", "password": "S" * 300},
        {"username": "maria", "password": 12345678901},
        {"username": "maria"},
    ],
)
def test_erro_422_no_login_nao_ecoa_a_senha(corpo):
    resposta = TestClient(create_app(_settings())).post(LOGIN, json=corpo)
    assert resposta.status_code == 422
    assert "input" not in resposta.text
    assert "S" * 300 not in resposta.text
    assert "12345678901" not in resposta.text


def test_422_das_demais_rotas_continua_padrao(client_autorizado):
    resposta = client_autorizado.get("/api/v1/transferencias/abc")
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["input"] == "abc"


@pytest.fixture
def cliente(db):
    app = create_app(_settings())
    app.dependency_overrides[get_session] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def maria(db):
    return criar_usuario(
        db, username="maria", nome_exibicao="Maria Silva", senha=SENHA, role="OPERADOR"
    )


def _login(cliente, username="maria", password=SENHA):
    return cliente.post(LOGIN, json={"username": username, "password": password})


def _token(cliente, **campos) -> str:
    resposta = _login(cliente, **campos)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["access_token"]


def _falha_generica(resposta) -> None:
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Usuário ou senha inválidos."}


@integration
def test_login_valido(cliente, db, maria):
    resposta = _login(cliente, username="  MARIA ")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"access_token", "token_type", "expires_in", "user"}
    assert corpo["token_type"] == "bearer"
    assert corpo["expires_in"] == 1800
    assert corpo["user"] == {
        "id": maria.id,
        "username": "maria",
        "nome_exibicao": "Maria Silva",
        "role": "OPERADOR",
        "ativo": True,
        "must_change_password": True,
        "sessao_continua": False,
    }
    assert validar_token_acesso(corpo["access_token"], SEGREDO).usuario_id == maria.id

    db.refresh(maria)
    assert maria.last_login_at is not None


@integration
def test_senha_invalida(cliente, db, maria):
    _falha_generica(_login(cliente, password="SenhaErrada123"))
    db.refresh(maria)
    assert maria.last_login_at is None


@integration
def test_usuario_inexistente_tem_a_mesma_resposta(cliente, maria):
    errada = _login(cliente, password="SenhaErrada123")
    inexistente = _login(cliente, username="ninguem")
    formato_invalido = _login(cliente, username="nome com espaco!")

    for resposta in (errada, inexistente, formato_invalido):
        _falha_generica(resposta)
    assert errada.headers.get("WWW-Authenticate") == inexistente.headers.get("WWW-Authenticate")


@integration
def test_usuario_inativo_nao_loga(cliente, db, maria):
    definir_ativo(db, maria, False)
    _falha_generica(_login(cliente))


@integration
def test_me_autenticado(cliente, maria):
    resposta = cliente.get(ME, headers=_bearer(_token(cliente)))
    assert resposta.status_code == 200
    assert resposta.json()["username"] == "maria"
    assert "password_hash" not in resposta.text


@integration
@pytest.mark.parametrize(
    "cabecalho",
    [
        {},
        {"Authorization": "Bearer lixo"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic bWFyaWE6c2VuaGE="},
        {"Authorization": "lixo"},
    ],
)
def test_me_sem_token_valido(cliente, maria, cabecalho):
    resposta = cliente.get(ME, headers=cabecalho)
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Não autenticado."}


@integration
def test_me_com_token_expirado(cliente, maria):
    token = _emitir(
        usuario_id=maria.id,
        password_changed_at=maria.password_changed_at,
        agora=datetime.now(UTC) - timedelta(hours=1),
    )
    assert cliente.get(ME, headers=_bearer(token)).status_code == 401


@integration
def test_me_com_token_de_outra_chave(cliente, maria):
    token = _emitir(
        usuario_id=maria.id,
        password_changed_at=maria.password_changed_at,
        segredo=secrets.token_urlsafe(48),
    )
    assert cliente.get(ME, headers=_bearer(token)).status_code == 401


@integration
def test_token_deixa_de_valer_se_usuario_for_desativado(cliente, db, maria):
    token = _token(cliente)
    definir_ativo(db, maria, False)
    assert cliente.get(ME, headers=_bearer(token)).status_code == 401


@integration
def test_token_de_usuario_removido_nao_vale(cliente, db, maria):
    token = _token(cliente)
    db.delete(maria)
    db.flush()
    assert cliente.get(ME, headers=_bearer(token)).status_code == 401


def _trocar(cliente, token, atual=SENHA, nova=NOVA_SENHA):
    return cliente.post(
        TROCA, headers=_bearer(token), json={"current_password": atual, "new_password": nova}
    )


@integration
def test_troca_de_senha_correta(cliente, db, maria):
    token_antigo = _token(cliente)
    antes = maria.password_changed_at

    resposta = _trocar(cliente, token_antigo)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["user"]["must_change_password"] is False
    assert SENHA not in resposta.text and NOVA_SENHA not in resposta.text
    assert "argon2" not in resposta.text

    db.refresh(maria)
    assert maria.must_change_password is False
    assert maria.password_changed_at > antes
    assert verificar_senha(NOVA_SENHA, maria.password_hash)
    assert not verificar_senha(SENHA, maria.password_hash)

    assert cliente.get(ME, headers=_bearer(corpo["access_token"])).status_code == 200
    assert cliente.get(ME, headers=_bearer(token_antigo)).status_code == 401

    _falha_generica(_login(cliente))
    assert _login(cliente, password=NOVA_SENHA).status_code == 200


@integration
def test_troca_com_senha_atual_incorreta(cliente, db, maria):
    token = _token(cliente)
    hash_antes = maria.password_hash

    resposta = _trocar(cliente, token, atual="SenhaErrada123")

    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "Senha atual incorreta."}
    db.refresh(maria)
    assert maria.password_hash == hash_antes
    assert maria.must_change_password is True


@integration
@pytest.mark.parametrize(
    ("nova", "regra"),
    [
        ("abc", "minimo de 4 caracteres"),
        (SENHA, "a nova senha deve ser diferente da atual"),
    ],
)
def test_troca_com_nova_senha_invalida(cliente, db, maria, nova, regra):
    token = _token(cliente)
    hash_antes = maria.password_hash

    resposta = _trocar(cliente, token, nova=nova)

    assert resposta.status_code == 422
    detalhe = resposta.json()["detail"]
    assert detalhe["mensagem"] == "Nova senha não atende à política."
    assert regra in detalhe["problemas"]
    assert nova not in resposta.text
    db.refresh(maria)
    assert maria.password_hash == hash_antes
    assert maria.must_change_password is True


@integration
def test_must_change_password_muda_para_false(cliente, db, maria):
    assert maria.must_change_password is True
    assert _login(cliente).json()["user"]["must_change_password"] is True

    _trocar(cliente, _token(cliente))

    novo = _login(cliente, password=NOVA_SENHA).json()
    assert novo["user"]["must_change_password"] is False


@integration
def test_logout_local(cliente, maria):
    resposta = cliente.post(LOGOUT, headers=_bearer(_token(cliente)))
    assert resposta.status_code == 204
    assert resposta.content == b""


@integration
def test_rate_limit_no_login(cliente, maria):
    for _ in range(5):
        _falha_generica(_login(cliente, password="SenhaErrada123"))

    for username in ("maria", "MARIA"):
        bloqueado = _login(cliente, username=username)
        assert bloqueado.status_code == 429
        assert bloqueado.json() == {"detail": "Muitas tentativas. Tente novamente mais tarde."}

    _falha_generica(_login(cliente, username="joao"))


@integration
def test_rate_limit_zera_apos_login_valido(cliente, maria):
    for _ in range(4):
        _login(cliente, password="SenhaErrada123")
    assert _login(cliente).status_code == 200
    for _ in range(4):
        _falha_generica(_login(cliente, password="SenhaErrada123"))
    assert _login(cliente).status_code == 200


@integration
def test_rate_limit_respeita_configuracao(db, maria):
    app = create_app(_settings(auth_login_rate_limit=2))
    app.dependency_overrides[get_session] = lambda: db
    cliente = TestClient(app)
    for _ in range(2):
        _login(cliente, password="SenhaErrada123")
    assert _login(cliente).status_code == 429


@integration
def test_rate_limit_na_troca_de_senha(cliente, maria):
    token = _token(cliente)
    for _ in range(5):
        assert _trocar(cliente, token, atual="SenhaErrada123").status_code == 400
    assert _trocar(cliente, token).status_code == 429


@integration
def test_logs_e_respostas_nao_expoem_senha_hash_ou_token(cliente, db, maria, caplog):
    caplog.set_level(logging.DEBUG)

    login = _login(cliente)
    token = login.json()["access_token"]
    falha = _login(cliente, password="SenhaErradaX99")
    me = cliente.get(ME, headers=_bearer(token))
    troca = _trocar(cliente, token)
    token_novo = troca.json()["access_token"]
    ruim = _trocar(cliente, token_novo, atual=NOVA_SENHA, nova="fracaSemNumero")
    logout = cliente.post(LOGOUT, headers=_bearer(token_novo))
    db.refresh(maria)

    segredos = [SENHA, NOVA_SENHA, "SenhaErradaX99", "fracaSemNumero", token, token_novo]
    segredos += [maria.password_hash, SEGREDO]
    for segredo in segredos:
        assert segredo not in caplog.text

    for resposta in (login, falha, me, troca, ruim, logout):
        for segredo in (SENHA, NOVA_SENHA, "SenhaErradaX99", "fracaSemNumero", SEGREDO):
            assert segredo not in resposta.text
        assert "argon2" not in resposta.text
        assert "password_hash" not in resposta.text

    assert "auth.login.sucesso" in caplog.text
    assert "auth.login.falha" in caplog.text
    assert "auth.troca_senha.sucesso" in caplog.text


def _modo_tv(db, usuario, ligado=True):
    usuario.must_change_password = False
    usuario.sessao_continua = ligado
    db.flush()


@integration
def test_renovacao_devolve_token_novo_para_sessao_continua(cliente, db, maria):
    _modo_tv(db, maria)
    token = _token(cliente)

    resposta = cliente.post(RENOVAR, headers=_bearer(token))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["expires_in"] == 1800
    assert corpo["user"]["sessao_continua"] is True
    assert validar_token_acesso(corpo["access_token"], SEGREDO).usuario_id == maria.id

    assert cliente.post(RENOVAR, headers=_bearer(corpo["access_token"])).status_code == 200


@integration
def test_renovacao_recusada_sem_sessao_continua(cliente, db, maria):
    _modo_tv(db, maria, ligado=False)
    resposta = cliente.post(RENOVAR, headers=_bearer(_token(cliente)))
    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "Renovação de sessão não habilitada para este usuário."}


@integration
def test_renovacao_recusada_com_troca_de_senha_pendente(cliente, db, maria):
    _modo_tv(db, maria)
    maria.must_change_password = True
    db.flush()
    assert cliente.post(RENOVAR, headers=_bearer(_token(cliente))).status_code == 403


@integration
def test_desligar_a_opcao_ou_desativar_para_a_renovacao(cliente, db, maria):
    _modo_tv(db, maria)
    token = _token(cliente)

    maria.sessao_continua = False
    db.flush()
    assert cliente.post(RENOVAR, headers=_bearer(token)).status_code == 403

    maria.sessao_continua = True
    definir_ativo(db, maria, False)
    db.flush()
    assert cliente.post(RENOVAR, headers=_bearer(token)).status_code == 401


@integration
def test_rate_limit_por_ip_pega_tentativas_em_varios_usuarios(db, maria):
    app = create_app(_settings(auth_login_ip_rate_limit=3))
    app.dependency_overrides[get_session] = lambda: db
    cliente = TestClient(app)
    for username in ("ana", "bruno", "carla"):
        _falha_generica(_login(cliente, username=username, password="Verao2026!"))

    assert _login(cliente, username="davi", password="Verao2026!").status_code == 429
    assert _login(cliente).status_code == 429


@integration
def test_renovacao_tem_idade_maxima_desde_o_login(cliente, db, maria):
    _modo_tv(db, maria)
    agora = datetime.now(UTC)
    antigo = emitir_token_acesso(
        usuario_id=maria.id,
        password_changed_at=maria.password_changed_at,
        segredo=SEGREDO,
        expira_minutos=30,
        inicio_sessao=agora - timedelta(days=8),
    )

    resposta = cliente.post(RENOVAR, headers=_bearer(antigo))

    assert resposta.status_code == 401
    assert "faça login" in resposta.json()["detail"]


@integration
def test_renovacao_mantem_o_inicio_da_sessao(cliente, db, maria):
    _modo_tv(db, maria)
    token = _token(cliente)
    inicio = validar_token_acesso(token, SEGREDO).inicio_sessao

    renovado = cliente.post(RENOVAR, headers=_bearer(token)).json()["access_token"]

    assert validar_token_acesso(renovado, SEGREDO).inicio_sessao == inicio


@integration
def test_logout_invalida_o_token_no_servidor(cliente, maria):
    token = _token(cliente)
    assert cliente.get(ME, headers=_bearer(token)).status_code == 200

    assert cliente.post(LOGOUT, headers=_bearer(token)).status_code == 204

    assert cliente.get(ME, headers=_bearer(token)).status_code == 401

    assert cliente.get(ME, headers=_bearer(_token(cliente))).status_code == 200
