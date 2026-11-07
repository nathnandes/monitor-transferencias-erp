from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS, Erro
from app.api.schemas_admin import (
    AtualizarUsuarioEntrada,
    CriarUsuarioEntrada,
    PaginaUsuarios,
    Papel,
    PermissoesAdmin,
    PermissoesEntrada,
    RedefinirSenhaEntrada,
    UsuarioAdmin,
    UsuarioAdminDetalhe,
)
from app.api.schemas_auth import ErroPolitica
from app.core.logging_config import get_logger
from app.core.seguranca import SenhaFracaError
from app.database.models import PerfilAcesso, Usuario
from app.dominio.modulos import Modulo
from app.services import admin_usuarios as service
from app.services import atividades
from app.services.autorizacao import PermissaoInvalidaError
from app.services.usuarios import UsernameEmUsoError, UsuarioInvalidoError, buscar_por_id

logger = get_logger(__name__)

router = APIRouter(
    prefix="/admin/users",
    tags=["admin"],
    dependencies=[Depends(exigir_modulo(Modulo.ADMINISTRACAO))],
    responses=RESPOSTAS_PROTEGIDAS,
)

TAMANHO_PAGINA_MAXIMO = 100
MSG_POLITICA = "Senha temporária não atende à política."
MSG_NAO_ENCONTRADO = "Usuário não encontrado."

Respostas = dict[int | str, dict[str, Any]]

_R404: Respostas = {404: {"model": Erro, "description": "Usuário não encontrado."}}
_R409: Respostas = {
    409: {"model": Erro, "description": "Regra de proteção (último ADMIN, a si mesmo)."}
}
_R422: Respostas = {
    422: {"model": ErroPolitica, "description": "Dado inválido ou senha fora da política."}
}

IdUsuario = Annotated[int, Path(description="Id interno do usuário.")]


def _alvo(db: Session, usuario_id: int) -> Usuario:
    usuario = buscar_por_id(db, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MSG_NAO_ENCONTRADO)
    return usuario


def _perfil(db: Session, perfil_id: int | None) -> PerfilAcesso | None:
    if perfil_id is None:
        return None
    perfil = db.get(PerfilAcesso, perfil_id)
    if perfil is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Perfil de acesso não encontrado."
        )
    return perfil


def _detalhe(db: Session, usuario: Usuario) -> UsuarioAdminDetalhe:

    db.refresh(usuario)
    return UsuarioAdminDetalhe.model_validate(
        {
            **UsuarioAdmin.model_validate(usuario).model_dump(),
            "modulos": service.modulos_do_usuario(db, usuario),
        }
    )


def _erro_de_regra(erro: Exception) -> HTTPException:
    if isinstance(erro, SenhaFracaError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"mensagem": MSG_POLITICA, "problemas": erro.problemas},
        )
    if isinstance(erro, UsuarioInvalidoError | PermissaoInvalidaError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro))
    if isinstance(erro, UsernameEmUsoError):
        return HTTPException(status.HTTP_409_CONFLICT, "Username já cadastrado.")
    if isinstance(erro, service.RegraAdministracaoError):
        return HTTPException(status.HTTP_409_CONFLICT, str(erro))
    raise TypeError(type(erro).__name__)


_ERROS_DE_REGRA = (
    SenhaFracaError,
    UsuarioInvalidoError,
    PermissaoInvalidaError,
    UsernameEmUsoError,
    service.RegraAdministracaoError,
)


@router.get("", summary="Lista usuários com busca, filtros e paginação")
def listar(
    db: SessionDep,
    admin: AdminDep,
    busca: Annotated[
        str | None,
        Query(
            max_length=100, description="Trecho de username ou nome, sem diferenciar maiúsculas."
        ),
    ] = None,
    ativo: Annotated[bool | None, Query(description="true = ativos; false = inativos.")] = None,
    role: Annotated[Papel | None, Query(description="ADMIN ou OPERADOR.")] = None,
    pagina: Annotated[int, Query(ge=1, description="Página, começando em 1.")] = 1,
    tamanho_pagina: Annotated[
        int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Itens por página.")
    ] = 20,
) -> PaginaUsuarios:
    resultado = service.listar_usuarios(
        db, busca=busca, ativo=ativo, role=role, pagina=pagina, tamanho_pagina=tamanho_pagina
    )
    return PaginaUsuarios(
        total=resultado.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(resultado.total / tamanho_pagina),
        itens=[UsuarioAdmin.model_validate(u) for u in resultado.itens],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Cria usuário ADMIN ou OPERADOR",
    description="`exigir_troca_senha` (padrão `true`) vira `must_change_password`.",
    responses={**_R409, **_R422},
)
def criar(dados: CriarUsuarioEntrada, db: SessionDep, admin: AdminDep) -> UsuarioAdminDetalhe:
    perfil = _perfil(db, dados.perfil_id)
    try:
        usuario = service.criar_usuario_administrado(
            db,
            ator=admin,
            username=dados.username,
            nome_exibicao=dados.nome_exibicao,
            senha=dados.password_temporaria,
            role=dados.role,
            modulos=dados.modulos,
            sessao_continua=dados.sessao_continua,
            must_change_password=dados.exigir_troca_senha,
            perfil=perfil,
        )
    except _ERROS_DE_REGRA as erro:
        raise _erro_de_regra(erro) from None
    atividades.registrar(
        db,
        "usuarios_alterados",
        f"{admin.nome_exibicao} criou o usuário {usuario.username} ({usuario.role})",
        usuario=admin,
    )
    db.commit()
    logger.info("admin.usuario.criado ator_id=%s alvo_id=%s", admin.id, usuario.id)
    return _detalhe(db, usuario)


@router.get("/{id}", summary="Detalha um usuário, com módulos", responses=_R404)
def detalhar(id: IdUsuario, db: SessionDep, admin: AdminDep) -> UsuarioAdminDetalhe:
    return _detalhe(db, _alvo(db, id))


@router.patch(
    "/{id}",
    summary="Altera nome, papel, ativo, módulos e perfil de acesso",
    description=(
        "Só os campos enviados mudam. `username` e senha não se alteram aqui "
        "(campo desconhecido → 422). Rebaixar ou desativar o último ADMIN ativo, "
        "ou alterar o próprio papel/ativo → 409."
    ),
    responses={**_R404, **_R409, **_R422},
)
def atualizar(
    id: IdUsuario, dados: AtualizarUsuarioEntrada, db: SessionDep, admin: AdminDep
) -> UsuarioAdminDetalhe:
    alvo = _alvo(db, id)

    muda_perfil = "perfil_id" in dados.model_fields_set
    perfil = _perfil(db, dados.perfil_id) if muda_perfil else None
    try:
        service.atualizar_usuario(
            db,
            ator=admin,
            alvo=alvo,
            nome_exibicao=dados.nome_exibicao,
            role=dados.role,
            ativo=dados.ativo,
            modulos=dados.modulos,
            sessao_continua=dados.sessao_continua,
        )
    except _ERROS_DE_REGRA as erro:
        raise _erro_de_regra(erro) from None
    if muda_perfil:
        service.definir_perfil(db, ator=admin, alvo=alvo, perfil=perfil)
    atividades.registrar(
        db,
        "usuarios_alterados",
        f"{admin.nome_exibicao} alterou o usuário {alvo.username}",
        usuario=admin,
        detalhe="Campos alterados: " + ", ".join(sorted(dados.model_fields_set)),
    )
    db.commit()
    logger.info("admin.usuario.atualizado ator_id=%s alvo_id=%s", admin.id, alvo.id)
    return _detalhe(db, alvo)


@router.post(
    "/{id}/reset-password",
    summary="Redefine a senha do usuário",
    description=(
        "Aplica a política de senha, define `must_change_password` conforme "
        "`exigir_troca_senha` (padrão `true`) e invalida os "
        "tokens já emitidos para o usuário. Não vale para o próprio ADMIN "
        "(use `/auth/change-password`)."
    ),
    responses={**_R404, **_R409, **_R422},
)
def redefinir_senha(
    id: IdUsuario, dados: RedefinirSenhaEntrada, db: SessionDep, admin: AdminDep
) -> UsuarioAdminDetalhe:
    alvo = _alvo(db, id)
    try:
        service.redefinir_senha(
            db,
            ator=admin,
            alvo=alvo,
            senha=dados.password_temporaria,
            must_change_password=dados.exigir_troca_senha,
        )
    except _ERROS_DE_REGRA as erro:
        raise _erro_de_regra(erro) from None
    atividades.registrar(
        db,
        "usuarios_alterados",
        f"{admin.nome_exibicao} redefiniu a senha de {alvo.username}",
        usuario=admin,
    )
    db.commit()
    logger.info("admin.usuario.senha_redefinida ator_id=%s alvo_id=%s", admin.id, alvo.id)
    return _detalhe(db, alvo)


def _alterar_ativo(db: Session, admin: Usuario, id: int, ativo: bool) -> UsuarioAdminDetalhe:
    alvo = _alvo(db, id)
    try:
        service.alterar_ativo(db, ator=admin, alvo=alvo, ativo=ativo)
    except _ERROS_DE_REGRA as erro:
        raise _erro_de_regra(erro) from None
    acao = "ativou" if ativo else "desativou"
    atividades.registrar(
        db,
        "usuarios_alterados",
        f"{admin.nome_exibicao} {acao} o usuário {alvo.username}",
        usuario=admin,
    )
    db.commit()
    evento = "ativado" if ativo else "desativado"
    logger.info("admin.usuario.%s ator_id=%s alvo_id=%s", evento, admin.id, alvo.id)
    return _detalhe(db, alvo)


@router.post("/{id}/activate", summary="Ativa um usuário", responses=_R404)
def ativar(id: IdUsuario, db: SessionDep, admin: AdminDep) -> UsuarioAdminDetalhe:
    return _alterar_ativo(db, admin, id, True)


@router.post(
    "/{id}/deactivate",
    summary="Desativa um usuário",
    description=(
        "Os tokens do usuário deixam de valer na hora. Recusado (409) para o último "
        "ADMIN ativo e para o próprio ADMIN."
    ),
    responses={**_R404, **_R409},
)
def desativar(id: IdUsuario, db: SessionDep, admin: AdminDep) -> UsuarioAdminDetalhe:
    return _alterar_ativo(db, admin, id, False)


@router.get("/{id}/permissions", summary="Módulos configurados do usuário", responses=_R404)
def permissoes(id: IdUsuario, db: SessionDep, admin: AdminDep) -> PermissoesAdmin:
    alvo = _alvo(db, id)
    return PermissoesAdmin(user_id=alvo.id, modulos=service.modulos_do_usuario(db, alvo))


@router.put(
    "/{id}/permissions",
    summary="Substitui os módulos do usuário",
    description=(
        "Envie o conjunto completo. Para ADMIN, `ADMINISTRACAO` é mantido sempre; "
        "para OPERADOR, `ADMINISTRACAO` → 422."
    ),
    responses={**_R404, **_R422},
)
def definir_permissoes(
    id: IdUsuario, dados: PermissoesEntrada, db: SessionDep, admin: AdminDep
) -> PermissoesAdmin:
    alvo = _alvo(db, id)
    try:
        service.definir_modulos(db, ator=admin, alvo=alvo, modulos=dados.modulos)
    except _ERROS_DE_REGRA as erro:
        raise _erro_de_regra(erro) from None
    atividades.registrar(
        db,
        "usuarios_alterados",
        f"{admin.nome_exibicao} mudou os módulos de {alvo.username}",
        usuario=admin,
        detalhe="Módulos: " + (", ".join(sorted(str(m) for m in dados.modulos)) or "nenhum"),
    )
    db.commit()
    logger.info("admin.usuario.permissoes ator_id=%s alvo_id=%s", admin.id, alvo.id)
    return PermissoesAdmin(user_id=alvo.id, modulos=service.modulos_do_usuario(db, alvo))
