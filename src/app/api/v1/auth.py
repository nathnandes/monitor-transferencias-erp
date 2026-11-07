from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.autenticacao import (
    ClaimsAcessoDep,
    ContextoAuth,
    ContextoAuthDep,
    UsuarioAutenticadoDep,
)
from app.api.deps import SessionDep
from app.api.schemas import Erro
from app.api.schemas_auth import (
    ErroPolitica,
    LoginEntrada,
    PermissoesUsuario,
    TokenAcesso,
    TrocaSenhaEntrada,
    UsuarioAutenticado,
)
from app.core.logging_config import get_logger
from app.core.seguranca import SenhaFracaError
from app.core.tokens import emitir_token_acesso
from app.database.models import Usuario
from app.services import atividades
from app.services.autorizacao import acesso_efetivo, ordenar
from app.services.usuarios import (
    NovaSenhaIgualError,
    SenhaAtualIncorretaError,
    UsuarioInvalidoError,
    normalizar_username,
    registrar_login,
    trocar_senha,
    validar_credenciais,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

MSG_CREDENCIAIS = "Usuário ou senha inválidos."
MSG_MUITAS_TENTATIVAS = "Muitas tentativas. Tente novamente mais tarde."
MSG_SENHA_ATUAL = "Senha atual incorreta."
MSG_POLITICA = "Nova senha não atende à política."
MSG_SEM_RENOVACAO = "Renovação de sessão não habilitada para este usuário."
MSG_SESSAO_EXPIRADA = "Sessão contínua expirou: faça login de novo."


def _ip(request: Request) -> str:

    return request.client.host if request.client else "desconhecido"


def _chave_login(username: str, ip: str) -> tuple[str, str, str]:
    try:
        normalizado = normalizar_username(username)
    except UsuarioInvalidoError:
        normalizado = username.strip().lower()[:64]
    return ("login", normalizado, ip)


def _muitas_tentativas() -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MSG_MUITAS_TENTATIVAS)


def _token(
    usuario: Usuario, contexto: ContextoAuth, inicio_sessao: datetime | None = None
) -> TokenAcesso:
    return TokenAcesso(
        access_token=emitir_token_acesso(
            usuario_id=usuario.id,
            password_changed_at=usuario.password_changed_at,
            segredo=contexto.segredo,
            expira_minutos=contexto.expira_minutos,
            inicio_sessao=inicio_sessao,
        ),
        expires_in=contexto.expira_minutos * 60,
        user=UsuarioAutenticado.model_validate(usuario),
    )


def _login_recusado(db: Session, username: str, motivo: str) -> None:
    digitado = username.strip()[:50] or "(vazio)"
    atividades.registrar(
        db,
        "login_recusado",
        f'Login recusado para "{digitado}"',
        usuario_nome=digitado,
        detalhe=f"Motivo: {motivo}.",
    )
    db.commit()


@router.post(
    "/login",
    summary="Login local por username e senha",
    responses={401: {"model": Erro}, 429: {"model": Erro}},
)
def login(
    dados: LoginEntrada, request: Request, db: SessionDep, contexto: ContextoAuthDep
) -> TokenAcesso:
    ip = _ip(request)
    chave = _chave_login(dados.username, ip)
    chave_ip = ("login_ip", ip)
    if contexto.limitador.bloqueado(chave) or contexto.limitador_ip.bloqueado(chave_ip):
        logger.warning("auth.login.bloqueado ip=%s", ip)
        _login_recusado(db, dados.username, "bloqueado por excesso de tentativas")
        raise _muitas_tentativas()

    usuario = validar_credenciais(db, dados.username, dados.password)
    if usuario is None:
        contexto.limitador.registrar_falha(chave)
        contexto.limitador_ip.registrar_falha(chave_ip)
        logger.warning("auth.login.falha ip=%s", ip)
        _login_recusado(db, dados.username, "usuário ou senha incorretos, ou usuário inativo")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, MSG_CREDENCIAIS, headers={"WWW-Authenticate": "Bearer"}
        )

    contexto.limitador.limpar(chave)
    registrar_login(db, usuario)
    atividades.registrar(db, "login", f"{usuario.nome_exibicao} entrou no sistema", usuario=usuario)
    db.commit()
    logger.info("auth.login.sucesso usuario_id=%s ip=%s", usuario.id, ip)
    return _token(usuario, contexto)


@router.get(
    "/me",
    summary="Dados do usuario autenticado",
    responses={401: {"model": Erro}},
)
def me(usuario: UsuarioAutenticadoDep) -> UsuarioAutenticado:
    return UsuarioAutenticado.model_validate(usuario)


@router.get(
    "/permissions",
    summary="Modulos, sub-abas e tela inicial do usuario autenticado",
    description=(
        "Calculado no servidor a partir do banco: o frontend usa para montar o menu, "
        "mas cada rota protegida confere a permissão de novo. `ADMINISTRACAO` "
        "aparece só para ADMIN. Com perfil de acesso, os módulos vêm do perfil, "
        "`abas` lista as sub-abas dele e `tela_inicial` é a tela que abre no login."
    ),
    responses={401: {"model": Erro}},
)
def permissions(usuario: UsuarioAutenticadoDep, db: SessionDep) -> PermissoesUsuario:
    acesso = acesso_efetivo(db, usuario)
    return PermissoesUsuario(
        modulos=ordenar(acesso.modulos),
        abas=None if acesso.abas is None else [a.value for a in acesso.abas],
        tela_inicial=acesso.tela_inicial,
    )


@router.post(
    "/change-password",
    summary="Troca a propria senha",
    description=(
        "Confere a senha atual e aplica a política (4 a 128 caracteres, diferente da "
        "atual). Devolve um **novo token**: o anterior deixa de valer."
    ),
    responses={
        400: {"model": Erro},
        401: {"model": Erro},
        422: {"model": ErroPolitica},
        429: {"model": Erro},
    },
)
def change_password(
    dados: TrocaSenhaEntrada,
    request: Request,
    db: SessionDep,
    contexto: ContextoAuthDep,
    usuario: UsuarioAutenticadoDep,
) -> TokenAcesso:
    ip = _ip(request)

    chave = ("troca-senha", usuario.id, ip)
    if contexto.limitador.bloqueado(chave):
        logger.warning("auth.troca_senha.bloqueada usuario_id=%s ip=%s", usuario.id, ip)
        raise _muitas_tentativas()

    try:
        trocar_senha(db, usuario, dados.current_password, dados.new_password)
    except SenhaAtualIncorretaError:
        contexto.limitador.registrar_falha(chave)
        logger.warning("auth.troca_senha.falha usuario_id=%s ip=%s", usuario.id, ip)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MSG_SENHA_ATUAL) from None
    except NovaSenhaIgualError as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"mensagem": MSG_POLITICA, "problemas": [str(erro)]},
        ) from None
    except SenhaFracaError as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"mensagem": MSG_POLITICA, "problemas": erro.problemas},
        ) from None

    contexto.limitador.limpar(chave)
    atividades.registrar(
        db, "senha_trocada", f"{usuario.nome_exibicao} trocou a própria senha", usuario=usuario
    )
    db.commit()
    logger.info("auth.troca_senha.sucesso usuario_id=%s", usuario.id)
    return _token(usuario, contexto)


@router.post(
    "/renew",
    summary="Renova o token (sessão contínua / modo TV)",
    description=(
        "Só para usuários com `sessao_continua` (OPERADOR, ligado pelo ADMIN). Devolve um "
        "token novo com a validade de sempre; o frontend chama antes de o atual expirar. "
        "Desativar o usuário, trocar a senha ou desligar a opção faz a renovação parar. "
        "A sessão tem idade máxima contada do login (`AUTH_SESSAO_CONTINUA_MAX_HORAS`, "
        "padrão 7 dias): depois disso, `401` e a TV pede login de novo."
    ),
    responses={401: {"model": Erro}, 403: {"model": Erro}},
)
def renew(
    contexto: ContextoAuthDep, usuario: UsuarioAutenticadoDep, claims: ClaimsAcessoDep
) -> TokenAcesso:

    if not usuario.sessao_continua or usuario.role == "ADMIN" or usuario.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, MSG_SEM_RENOVACAO)
    if datetime.now(UTC) - claims.inicio_sessao > contexto.sessao_continua_max:
        logger.info("auth.renovacao.expirada usuario_id=%s", usuario.id)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            MSG_SESSAO_EXPIRADA,
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("auth.renovacao usuario_id=%s", usuario.id)
    return _token(usuario, contexto, inicio_sessao=claims.inicio_sessao)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout local",
    description=(
        "O token usado deixa de valer na hora (revogado na memória da API até "
        "expirar); o frontend descarta o token e, na sessão contínua, para de "
        "renová-lo. Reiniciar a API esquece as revogações: os tokens ainda expiram "
        "sozinhos (JWT_ACCESS_TOKEN_EXPIRE_MINUTES)."
    ),
    responses={401: {"model": Erro}},
)
def logout(
    usuario: UsuarioAutenticadoDep,
    claims: ClaimsAcessoDep,
    contexto: ContextoAuthDep,
    db: SessionDep,
) -> Response:
    if claims.jti:
        contexto.revogados.revogar(claims.jti, claims.expira_em)
    atividades.registrar(db, "logout", f"{usuario.nome_exibicao} saiu do sistema", usuario=usuario)
    db.commit()
    logger.info("auth.logout usuario_id=%s", usuario.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
