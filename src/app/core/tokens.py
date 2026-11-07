import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

ALGORITMO = "HS256"
EMISSOR = "erp-automation"
TIPO_ACESSO = "access"
SEGREDO_MIN_CARACTERES = 32

_EPOCA = datetime(1970, 1, 1, tzinfo=UTC)
_SEGREDOS_OBVIOS = {"changeme", "change-me", "secret", "segredo", "jwt_secret", "senha", "password"}


class ConfiguracaoInseguraError(RuntimeError):
    pass


class TokenInvalidoError(Exception):
    pass


@dataclass(frozen=True)
class ClaimsAcesso:
    usuario_id: int
    versao_senha: int

    inicio_sessao: datetime
    expira_em: datetime
    jti: str | None = None


def problemas_do_segredo(segredo: str) -> list[str]:
    problemas: list[str] = []
    if len(segredo) < SEGREDO_MIN_CARACTERES:
        problemas.append(f"menos de {SEGREDO_MIN_CARACTERES} caracteres")
    if len(set(segredo)) < 10:
        problemas.append("pouca variedade de caracteres")
    if segredo.strip().lower() in _SEGREDOS_OBVIOS:
        problemas.append("valor obvio")
    return problemas


def resolver_segredo(settings: Settings) -> str:
    segredo = settings.jwt_secret.get_secret_value()
    if settings.is_production:
        if not segredo:
            raise ConfiguracaoInseguraError("JWT_SECRET ausente em producao")
        problemas = problemas_do_segredo(segredo)
        if problemas:
            raise ConfiguracaoInseguraError("JWT_SECRET fraco em producao: " + "; ".join(problemas))
        return segredo

    if not segredo:
        logger.warning(
            "JWT_SECRET vazio: usando chave aleatoria deste processo; "
            "tokens deixam de valer ao reiniciar a API"
        )
        return secrets.token_urlsafe(48)
    if problemas_do_segredo(segredo):
        logger.warning("JWT_SECRET fraco: aceito fora de producao, recusado em producao")
    return segredo


def versao_da_senha(password_changed_at: datetime | None) -> int:
    if password_changed_at is None:
        return 0
    return (password_changed_at - _EPOCA) // timedelta(microseconds=1)


def emitir_token_acesso(
    *,
    usuario_id: int,
    password_changed_at: datetime | None,
    segredo: str,
    expira_minutos: int,
    agora: datetime | None = None,
    inicio_sessao: datetime | None = None,
) -> str:
    agora = agora or datetime.now(UTC)
    claims = {
        "sub": str(usuario_id),
        "typ": TIPO_ACESSO,
        "iss": EMISSOR,
        "iat": agora,
        "exp": agora + timedelta(minutes=expira_minutos),
        "pwv": versao_da_senha(password_changed_at),
        "ses": int((inicio_sessao or agora).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(claims, segredo, algorithm=ALGORITMO)


def validar_token_acesso(token: str, segredo: str) -> ClaimsAcesso:
    try:
        claims = jwt.decode(
            token,
            segredo,
            algorithms=[ALGORITMO],
            issuer=EMISSOR,
            options={"require": ["sub", "typ", "iss", "iat", "exp", "pwv"]},
        )
        if claims["typ"] != TIPO_ACESSO:
            raise TokenInvalidoError

        inicio = int(claims.get("ses", claims["iat"]))
        return ClaimsAcesso(
            usuario_id=int(claims["sub"]),
            versao_senha=int(claims["pwv"]),
            inicio_sessao=datetime.fromtimestamp(inicio, UTC),
            expira_em=datetime.fromtimestamp(int(claims["exp"]), UTC),
            jti=str(claims["jti"]) if claims.get("jti") else None,
        )
    except (jwt.PyJWTError, ValueError, TypeError):
        raise TokenInvalidoError from None
