import secrets
from functools import lru_cache

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

SENHA_MIN_CARACTERES = 4

SENHA_MAX_CARACTERES = 128

_hasher = PasswordHasher(type=Type.ID)


class SenhaFracaError(ValueError):
    def __init__(self, problemas: list[str]) -> None:
        self.problemas = problemas
        super().__init__("senha nao atende a politica: " + "; ".join(problemas))


def problemas_da_senha(senha: str) -> list[str]:
    problemas: list[str] = []
    if len(senha) < SENHA_MIN_CARACTERES:
        problemas.append(f"minimo de {SENHA_MIN_CARACTERES} caracteres")
    if len(senha) > SENHA_MAX_CARACTERES:
        problemas.append(f"maximo de {SENHA_MAX_CARACTERES} caracteres")
    return problemas


def validar_senha(senha: str) -> None:
    problemas = problemas_da_senha(senha)
    if problemas:
        raise SenhaFracaError(problemas)


def gerar_hash_senha(senha: str) -> str:
    validar_senha(senha)
    return _hasher.hash(senha)


def verificar_senha(senha: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, senha)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def _hash_ficticio() -> str:

    return _hasher.hash(secrets.token_urlsafe(32))


def simular_verificacao(senha: str) -> None:
    verificar_senha(senha, _hash_ficticio())


def precisa_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
