from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import SessionDep
from app.core.config import Settings
from app.core.limite_tentativas import LimitadorTentativas
from app.core.revogacao import TokensRevogados
from app.core.tokens import (
    ClaimsAcesso,
    TokenInvalidoError,
    resolver_segredo,
    validar_token_acesso,
    versao_da_senha,
)
from app.database.models import Usuario
from app.database.session import liberar_conexao
from app.services.usuarios import buscar_por_id

MSG_NAO_AUTENTICADO = "Não autenticado."


@dataclass(frozen=True)
class ContextoAuth:
    segredo: str
    expira_minutos: int
    limitador: LimitadorTentativas

    limitador_ip: LimitadorTentativas

    revogados: TokensRevogados
    sessao_continua_max: timedelta


def criar_contexto_auth(settings: Settings) -> ContextoAuth:
    return ContextoAuth(
        segredo=resolver_segredo(settings),
        expira_minutos=settings.jwt_access_token_expire_minutes,
        limitador=LimitadorTentativas(
            settings.auth_login_rate_limit, settings.auth_login_rate_window_seconds
        ),
        limitador_ip=LimitadorTentativas(
            settings.auth_login_ip_rate_limit, settings.auth_login_rate_window_seconds
        ),
        revogados=TokensRevogados(),
        sessao_continua_max=timedelta(hours=settings.auth_sessao_continua_max_horas),
    )


def get_contexto_auth(request: Request) -> ContextoAuth:
    contexto: ContextoAuth = request.app.state.auth
    return contexto


ContextoAuthDep = Annotated[ContextoAuth, Depends(get_contexto_auth)]


_bearer = HTTPBearer(
    scheme_name="BearerJWT",
    description="Cole o access_token devolvido por POST /api/v1/auth/login.",
    auto_error=False,
)


def nao_autenticado() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=MSG_NAO_AUTENTICADO,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_usuario_autenticado(
    request: Request,
    db: SessionDep,
    contexto: ContextoAuthDep,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if credenciais is None or credenciais.scheme.lower() != "bearer":
        raise nao_autenticado()
    try:
        claims = validar_token_acesso(credenciais.credentials, contexto.segredo)
    except TokenInvalidoError:
        raise nao_autenticado() from None
    if claims.jti and contexto.revogados.revogado(claims.jti):
        raise nao_autenticado()

    usuario = buscar_por_id(db, claims.usuario_id)
    if (
        usuario is None
        or not usuario.ativo
        or versao_da_senha(usuario.password_changed_at) != claims.versao_senha
    ):
        raise nao_autenticado()
    request.state.claims_acesso = claims
    liberar_conexao(db)
    return usuario


UsuarioAutenticadoDep = Annotated[Usuario, Depends(get_usuario_autenticado)]


def get_claims_acesso(request: Request, _usuario: UsuarioAutenticadoDep) -> ClaimsAcesso:
    claims: ClaimsAcesso = request.state.claims_acesso
    return claims


ClaimsAcessoDep = Annotated[ClaimsAcesso, Depends(get_claims_acesso)]
