import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.seguranca import gerar_hash_senha, simular_verificacao, verificar_senha
from app.database.models import PAPEIS_USUARIO, Usuario
from app.services.autorizacao import aplicar_permissoes_iniciais

USERNAME_MIN = 3
USERNAME_MAX = 50
NOME_EXIBICAO_MAX = 100

_USERNAME = re.compile(rf"^[a-z0-9._-]{{{USERNAME_MIN},{USERNAME_MAX}}}$")


class UsuarioInvalidoError(ValueError):
    pass


class UsernameEmUsoError(ValueError):
    pass


class SenhaAtualIncorretaError(ValueError):
    pass


class NovaSenhaIgualError(ValueError):
    pass


def normalizar_username(valor: str) -> str:
    username = valor.strip().lower()
    if not _USERNAME.fullmatch(username):
        raise UsuarioInvalidoError(
            f"username deve ter de {USERNAME_MIN} a {USERNAME_MAX} caracteres, "
            "apenas letras, numeros, ponto, hifen e underscore"
        )
    return username


def normalizar_nome_exibicao(valor: str) -> str:
    nome = valor.strip()
    if not nome:
        raise UsuarioInvalidoError("nome de exibicao e obrigatorio")
    if len(nome) > NOME_EXIBICAO_MAX:
        raise UsuarioInvalidoError(
            f"nome de exibicao deve ter no maximo {NOME_EXIBICAO_MAX} caracteres"
        )
    return nome


def validar_role(valor: str) -> str:
    if valor not in PAPEIS_USUARIO:
        raise UsuarioInvalidoError(f"role deve ser um de: {', '.join(PAPEIS_USUARIO)}")
    return valor


def buscar_por_username(session: Session, username: str) -> Usuario | None:
    try:
        normalizado = normalizar_username(username)
    except UsuarioInvalidoError:
        return None
    return session.scalar(select(Usuario).where(Usuario.username == normalizado))


def criar_usuario(
    session: Session,
    *,
    username: str,
    nome_exibicao: str,
    senha: str,
    role: str,
    must_change_password: bool = True,
) -> Usuario:
    username = normalizar_username(username)
    nome_exibicao = normalizar_nome_exibicao(nome_exibicao)
    role = validar_role(role)

    if buscar_por_username(session, username) is not None:
        raise UsernameEmUsoError(f"username ja cadastrado: {username}")

    usuario = Usuario(
        username=username,
        nome_exibicao=nome_exibicao,
        password_hash=gerar_hash_senha(senha),
        role=role,
        must_change_password=must_change_password,
        password_changed_at=datetime.now(UTC),
    )
    try:
        with session.begin_nested():
            session.add(usuario)
            session.flush()
    except IntegrityError as erro:
        diag = getattr(erro.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == "uq_users_username":
            raise UsernameEmUsoError(f"username ja cadastrado: {username}") from None
        raise
    aplicar_permissoes_iniciais(session, usuario)
    return usuario


def validar_credenciais(session: Session, username: str, senha: str) -> Usuario | None:
    usuario = buscar_por_username(session, username)
    if usuario is None:
        simular_verificacao(senha)
        return None
    senha_confere = verificar_senha(senha, usuario.password_hash)
    if not senha_confere or not usuario.ativo:
        return None
    return usuario


def definir_ativo(session: Session, usuario: Usuario, ativo: bool) -> None:
    usuario.ativo = ativo
    session.flush()


def buscar_por_id(session: Session, usuario_id: int) -> Usuario | None:
    return session.get(Usuario, usuario_id)


def registrar_login(session: Session, usuario: Usuario) -> None:
    usuario.last_login_at = datetime.now(UTC)
    session.flush()


def trocar_senha(session: Session, usuario: Usuario, senha_atual: str, nova_senha: str) -> None:
    if not verificar_senha(senha_atual, usuario.password_hash):
        raise SenhaAtualIncorretaError("senha atual incorreta")
    if nova_senha == senha_atual:
        raise NovaSenhaIgualError("a nova senha deve ser diferente da atual")
    usuario.password_hash = gerar_hash_senha(nova_senha)
    usuario.password_changed_at = datetime.now(UTC)
    usuario.must_change_password = False
    session.flush()
