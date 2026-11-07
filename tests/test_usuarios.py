import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from app.core.logging_config import FormatterMascarado
from app.core.mascaramento import mascarar_texto
from app.core.seguranca import (
    SenhaFracaError,
    gerar_hash_senha,
    precisa_rehash,
    problemas_da_senha,
    validar_senha,
    verificar_senha,
)
from app.database.models import Usuario
from app.services.usuarios import (
    UsernameEmUsoError,
    UsuarioInvalidoError,
    buscar_por_username,
    criar_usuario,
    definir_ativo,
    normalizar_nome_exibicao,
    normalizar_username,
    validar_credenciais,
    validar_role,
)

RAIZ = Path(__file__).resolve().parent.parent
SENHA = "SenhaForte123"


@pytest.mark.parametrize(
    ("senha", "regra"),
    [
        ("abc", "minimo de 4 caracteres"),
        ("Aa1" + "x" * 126, "maximo de 128 caracteres"),
    ],
)
def test_senha_fora_da_politica_e_rejeitada(senha, regra):
    assert regra in problemas_da_senha(senha)
    with pytest.raises(SenhaFracaError) as erro:
        validar_senha(senha)
    assert regra in erro.value.problemas


def test_senha_valida_passa():
    assert problemas_da_senha(SENHA) == []
    assert problemas_da_senha("1234") == []
    assert problemas_da_senha("loja") == []


def test_erro_de_senha_fraca_nao_expoe_a_senha():
    with pytest.raises(SenhaFracaError) as erro:
        validar_senha("xyz")
    assert "xyz" not in str(erro.value)


def test_hash_e_argon2id_com_salt_e_sem_texto_puro():
    h1, h2 = gerar_hash_senha(SENHA), gerar_hash_senha(SENHA)
    assert h1.startswith("$argon2id$")
    assert SENHA not in h1
    assert h1 != h2


def test_verificacao_de_senha():
    h = gerar_hash_senha(SENHA)
    assert verificar_senha(SENHA, h)
    assert not verificar_senha("SenhaErrada123", h)
    assert not verificar_senha(SENHA.lower(), h)


@pytest.mark.parametrize("hash_ruim", ["", "texto-puro", SENHA, "$argon2id$quebrado"])
def test_hash_invalido_nao_levanta_e_nao_confere(hash_ruim):
    assert verificar_senha(SENHA, hash_ruim) is False


def test_hash_nao_gera_para_senha_fraca():
    with pytest.raises(SenhaFracaError):
        gerar_hash_senha("abc")


def test_precisa_rehash():
    assert precisa_rehash(gerar_hash_senha(SENHA)) is False
    assert precisa_rehash("nao-e-hash") is True


def test_hash_argon2_e_mascarado_em_qualquer_posicao():
    h = gerar_hash_senha(SENHA)
    for linha in (f"hash {h} gravado", f"password_hash={h}", f'{{"password_hash": "{h}"}}'):
        mascarado = mascarar_texto(linha)
        assert h not in mascarado

        for parte in h.split("$")[-2:]:
            assert parte not in mascarado


def test_formatter_da_aplicacao_mascara_hash_e_senha():
    h = gerar_hash_senha(SENHA)
    registro = logging.LogRecord(
        "teste", logging.INFO, __file__, 1, "senha=%s hash=%s", (SENHA, h), None
    )
    saida = FormatterMascarado().format(registro)
    assert SENHA not in saida
    assert h not in saida


def test_repr_do_usuario_nao_expoe_hash():
    u = Usuario(username="maria", role="OPERADOR", password_hash=gerar_hash_senha(SENHA))
    assert "argon2" not in repr(u)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Maria", "maria"),
        ("  JOAO.Silva  ", "joao.silva"),
        ("op_01", "op_01"),
        ("ana-paula", "ana-paula"),
        ("abc", "abc"),
        ("a" * 50, "a" * 50),
    ],
)
def test_username_normalizado(entrada, esperado):
    assert normalizar_username(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", "   ", "ab", "a" * 51, "maria silva", "maria@loja", "joão", "ana/b", "x;drop"],
)
def test_username_fora_do_formato_e_rejeitado(entrada):
    with pytest.raises(UsuarioInvalidoError):
        normalizar_username(entrada)


@pytest.mark.parametrize("entrada", ["", "   ", "x" * 101])
def test_nome_exibicao_invalido(entrada):
    with pytest.raises(UsuarioInvalidoError):
        normalizar_nome_exibicao(entrada)


def test_nome_exibicao_sem_espacos_nas_pontas():
    assert normalizar_nome_exibicao("  Maria Silva ") == "Maria Silva"


@pytest.mark.parametrize("role", ["admin", "Operador", "GERENTE", ""])
def test_role_fora_da_lista_e_rejeitada(role):
    with pytest.raises(UsuarioInvalidoError):
        validar_role(role)


integration = pytest.mark.integration


def _criar(db, username="maria", role="OPERADOR", **campos) -> Usuario:
    return criar_usuario(
        db, username=username, nome_exibicao="Maria", senha=SENHA, role=role, **campos
    )


def _viola(db, constraint: str, sql: str, **params) -> None:
    with pytest.raises(IntegrityError) as erro:
        with db.begin_nested():
            db.execute(text(sql), params)
    assert erro.value.orig.diag.constraint_name == constraint


_INSERT = (
    "INSERT INTO users (username, nome_exibicao, password_hash, role)"
    " VALUES (:username, :nome, :hash, :role)"
)


@pytest.fixture
def hash_valido() -> str:
    return gerar_hash_senha(SENHA)


@integration
def test_criar_usuario_com_padroes(db):
    u = _criar(db, username="  Maria.Silva ")
    db.refresh(u)

    assert u.id is not None
    assert u.username == "maria.silva"
    assert u.ativo is True
    assert u.must_change_password is True
    assert u.last_login_at is None
    assert u.password_changed_at is not None
    assert u.created_at is not None and u.updated_at is not None
    assert u.password_hash.startswith("$argon2id$")
    assert verificar_senha(SENHA, u.password_hash)


@integration
def test_username_duplicado_ignorando_maiusculas(db):
    _criar(db, username="maria")
    with pytest.raises(UsernameEmUsoError):
        _criar(db, username="MARIA")

    assert buscar_por_username(db, "Maria") is not None


@integration
def test_busca_ignora_maiusculas_e_formato_invalido(db):
    _criar(db, username="joao")
    assert buscar_por_username(db, "JoAo").username == "joao"
    assert buscar_por_username(db, "nao existe!") is None


@integration
def test_credenciais_corretas_de_usuario_ativo(db):
    u = _criar(db, username="maria")
    assert validar_credenciais(db, "MARIA", SENHA) is u


@integration
def test_senha_incorreta_falha(db):
    _criar(db, username="maria")
    assert validar_credenciais(db, "maria", "SenhaErrada123") is None
    assert validar_credenciais(db, "maria", SENHA.upper()) is None


@integration
def test_usuario_inexistente_falha(db):
    assert validar_credenciais(db, "ninguem", SENHA) is None


@integration
def test_usuario_inativo_nao_valida_e_reativado_volta(db):
    u = _criar(db, username="maria")

    definir_ativo(db, u, False)
    db.refresh(u)
    assert u.ativo is False
    assert validar_credenciais(db, "maria", SENHA) is None

    definir_ativo(db, u, True)
    db.refresh(u)
    assert u.ativo is True
    assert validar_credenciais(db, "maria", SENHA) is u


@integration
def test_validar_credenciais_nao_e_login(db):
    u = _criar(db)
    validar_credenciais(db, "maria", SENHA)
    db.refresh(u)
    assert u.last_login_at is None
    assert u.must_change_password is True


@integration
def test_schema_users_no_banco(db):
    constraints = set(
        db.scalars(text("SELECT conname FROM pg_constraint WHERE conrelid = 'users'::regclass"))
    )
    assert {
        "users_pkey",
        "uq_users_username",
        "ck_users_username_formato",
        "ck_users_nome_exibicao_preenchido",
        "ck_users_role",
        "ck_users_password_hash_argon2id",
        "ck_users_sessao_continua_so_operador",
    } <= constraints

    colunas = {
        linha.column_name: linha
        for linha in db.execute(
            text(
                "SELECT column_name, is_nullable, column_default"
                " FROM information_schema.columns WHERE table_name = 'users'"
            )
        )
    }
    assert set(colunas) == {
        "id",
        "username",
        "nome_exibicao",
        "password_hash",
        "role",
        "ativo",
        "must_change_password",
        "sessao_continua",
        "perfil_id",
        "last_login_at",
        "password_changed_at",
        "created_at",
        "updated_at",
    }
    opcionais = {n for n, c in colunas.items() if c.is_nullable == "YES"}
    assert opcionais == {"perfil_id", "last_login_at", "password_changed_at"}
    assert colunas["ativo"].column_default == "true"
    assert colunas["must_change_password"].column_default == "true"


def test_migration_nao_cria_usuarios():
    fonte = (RAIZ / "migrations" / "versions" / "0003_users.py").read_text(encoding="utf-8")
    for proibido in ("insert", "bulk_insert", "op.execute"):
        assert proibido not in fonte.lower(), proibido


@integration
def test_banco_rejeita_senha_em_texto_puro(db):
    _viola(
        db,
        "ck_users_password_hash_argon2id",
        _INSERT,
        username="maria",
        nome="Maria",
        hash=SENHA,
        role="OPERADOR",
    )


@integration
@pytest.mark.parametrize("username", ["Maria", "ab", "maria silva", "maria@x", ""])
def test_banco_rejeita_username_fora_do_formato(db, hash_valido, username):
    _viola(
        db,
        "ck_users_username_formato",
        _INSERT,
        username=username,
        nome="Maria",
        hash=hash_valido,
        role="OPERADOR",
    )


@integration
def test_banco_rejeita_username_duplicado(db, hash_valido):
    params = {"username": "maria", "nome": "Maria", "hash": hash_valido, "role": "OPERADOR"}
    db.execute(text(_INSERT), params)
    _viola(db, "uq_users_username", _INSERT, **params)


@integration
@pytest.mark.parametrize("nome", ["", "   "])
def test_banco_rejeita_nome_exibicao_vazio(db, hash_valido, nome):
    _viola(
        db,
        "ck_users_nome_exibicao_preenchido",
        _INSERT,
        username="maria",
        nome=nome,
        hash=hash_valido,
        role="OPERADOR",
    )


@integration
@pytest.mark.parametrize("role", ["admin", "GERENTE", ""])
def test_banco_rejeita_role_invalida(db, hash_valido, role):
    _viola(
        db,
        "ck_users_role",
        _INSERT,
        username="maria",
        nome="Maria",
        hash=hash_valido,
        role=role,
    )


@integration
def test_updated_at_muda_no_update(db):
    u = _criar(db)
    antigo = datetime(2020, 1, 1, tzinfo=UTC)
    db.execute(
        update(Usuario).where(Usuario.id == u.id).values(created_at=antigo, updated_at=antigo)
    )
    db.refresh(u)
    u.nome_exibicao = "Maria S."
    db.flush()
    db.refresh(u)
    assert u.updated_at > u.created_at
