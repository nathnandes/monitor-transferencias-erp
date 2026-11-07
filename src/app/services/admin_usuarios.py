from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.seguranca import gerar_hash_senha
from app.database.models import PerfilAcesso, Usuario
from app.dominio.modulos import Modulo
from app.services.auditoria import OrigemAuditoria, TipoEventoAuditoria, registrar_evento
from app.services.autorizacao import (
    PAPEL_ADMIN,
    PermissaoInvalidaError,
    aplicar_permissoes_iniciais,
    conceder_permissao,
    modulos_configurados,
    ordenar,
    revogar_permissao,
    validar_modulo,
)
from app.services.usuarios import (
    criar_usuario,
    normalizar_nome_exibicao,
    validar_role,
)

MSG_ULTIMO_ADMIN = "Operação recusada: o sistema ficaria sem nenhum ADMIN ativo."
MSG_PROPRIO_USUARIO = (
    "Operação recusada: um ADMIN não pode desativar a si mesmo, mudar o próprio papel "
    "ou redefinir a própria senha por aqui. Peça a outro ADMIN."
)


class RegraAdministracaoError(ValueError):
    pass


@dataclass(frozen=True)
class Pagina:
    total: int
    itens: list[Usuario]


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar_usuarios(
    session: Session,
    *,
    busca: str | None = None,
    ativo: bool | None = None,
    role: str | None = None,
    pagina: int = 1,
    tamanho_pagina: int = 20,
) -> Pagina:
    consulta = select(Usuario)
    if busca and busca.strip():
        padrao = f"%{_escapar_like(busca.strip())}%"
        consulta = consulta.where(
            or_(
                Usuario.username.ilike(padrao, escape="\\"),
                Usuario.nome_exibicao.ilike(padrao, escape="\\"),
            )
        )
    if ativo is not None:
        consulta = consulta.where(Usuario.ativo.is_(ativo))
    if role is not None:
        consulta = consulta.where(Usuario.role == validar_role(role))

    total = session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = session.scalars(
        consulta.order_by(Usuario.username, Usuario.id)
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
    ).all()
    return Pagina(total=total, itens=list(itens))


def modulos_do_usuario(session: Session, usuario: Usuario) -> list[Modulo]:
    return ordenar(modulos_configurados(session, usuario))


def _eh_admin(usuario: Usuario) -> bool:
    return usuario.role == PAPEL_ADMIN


def _garantir_admin_restante(session: Session, alvo: Usuario) -> None:
    ids = set(
        session.scalars(
            select(Usuario.id)
            .where(Usuario.role == PAPEL_ADMIN, Usuario.ativo.is_(True))
            .with_for_update()
        )
    )
    if alvo.id in ids and not ids - {alvo.id}:
        raise RegraAdministracaoError(MSG_ULTIMO_ADMIN)


def _nao_em_si_mesmo(ator: Usuario | None, alvo: Usuario) -> None:
    if ator is not None and ator.id == alvo.id:
        raise RegraAdministracaoError(MSG_PROPRIO_USUARIO)


def _proteger_saida_de_admin(session: Session, ator: Usuario | None, alvo: Usuario) -> None:
    if _eh_admin(alvo) and alvo.ativo:
        _garantir_admin_restante(session, alvo)
    _nao_em_si_mesmo(ator, alvo)


def validar_modulos(role: str, modulos: Iterable[str]) -> frozenset[Modulo]:
    desejados = {validar_modulo(m) for m in modulos}
    if role == PAPEL_ADMIN:
        desejados.add(Modulo.ADMINISTRACAO)
    elif Modulo.ADMINISTRACAO in desejados:
        raise PermissaoInvalidaError("ADMINISTRACAO so pode ser atribuida a ADMIN")
    return frozenset(desejados)


def _aplicar_modulos(session: Session, usuario: Usuario, desejados: frozenset[Modulo]) -> None:
    for modulo in Modulo:
        if modulo in desejados:
            conceder_permissao(session, usuario, modulo)
        elif not (modulo is Modulo.ADMINISTRACAO and _eh_admin(usuario)):
            revogar_permissao(session, usuario, modulo)


def _auditar_modulos(
    session: Session,
    *,
    ator: Usuario | None,
    alvo: Usuario,
    antes: frozenset[Modulo],
    origem: OrigemAuditoria,
) -> None:
    depois = modulos_configurados(session, alvo)
    if depois == antes:
        return
    registrar_evento(
        session,
        TipoEventoAuditoria.PERMISSOES_ALTERADAS,
        alvo=alvo,
        ator=ator,
        origem=origem,
        detalhes={
            "modulos_concedidos": [str(m) for m in ordenar(depois - antes)],
            "modulos_revogados": [str(m) for m in ordenar(antes - depois)],
        },
    )


def validar_sessao_continua(role: str, sessao_continua: bool) -> None:
    if sessao_continua and role == PAPEL_ADMIN:
        raise RegraAdministracaoError(
            "Sessão contínua (modo TV) é só para OPERADOR: uma sessão de administrador "
            "esquecida aberta numa TV daria acesso à administração."
        )


def criar_usuario_administrado(
    session: Session,
    *,
    ator: Usuario | None,
    username: str,
    nome_exibicao: str,
    senha: str,
    role: str,
    modulos: Iterable[str] | None = None,
    must_change_password: bool = True,
    sessao_continua: bool = False,
    perfil: PerfilAcesso | None = None,
    origem: OrigemAuditoria = OrigemAuditoria.API,
) -> Usuario:
    role = validar_role(role)
    desejados = validar_modulos(role, modulos) if modulos is not None else None
    validar_sessao_continua(role, sessao_continua)

    usuario = criar_usuario(
        session,
        username=username,
        nome_exibicao=nome_exibicao,
        senha=senha,
        role=role,
        must_change_password=must_change_password,
    )
    if desejados is not None:
        _aplicar_modulos(session, usuario, desejados)
    if sessao_continua:
        usuario.sessao_continua = True
        session.flush()
    if perfil is not None:
        usuario.perfil = perfil
        session.flush()

    registrar_evento(
        session,
        TipoEventoAuditoria.USUARIO_CRIADO,
        alvo=usuario,
        ator=ator,
        origem=origem,
        detalhes={
            "role": role,
            "modulos": [str(m) for m in modulos_do_usuario(session, usuario)],
            "sessao_continua": sessao_continua,
            "exigir_troca": must_change_password,
            **({"perfil_novo": perfil.nome} if perfil else {}),
        },
    )
    return usuario


def definir_perfil(
    session: Session, *, ator: Usuario | None, alvo: Usuario, perfil: PerfilAcesso | None
) -> None:
    if alvo.perfil_id == (perfil.id if perfil else None):
        return
    anterior = alvo.perfil.nome if alvo.perfil else ""
    alvo.perfil = perfil
    session.flush()
    registrar_evento(
        session,
        TipoEventoAuditoria.USUARIO_EDITADO,
        alvo=alvo,
        ator=ator,
        detalhes={
            "campos": ["perfil"],
            "perfil_anterior": anterior,
            "perfil_novo": perfil.nome if perfil else "",
        },
    )


def alterar_ativo(session: Session, *, ator: Usuario | None, alvo: Usuario, ativo: bool) -> None:
    if alvo.ativo == ativo:
        return
    if not ativo:
        _proteger_saida_de_admin(session, ator, alvo)
    alvo.ativo = ativo
    session.flush()
    registrar_evento(
        session,
        TipoEventoAuditoria.USUARIO_ATIVADO if ativo else TipoEventoAuditoria.USUARIO_DESATIVADO,
        alvo=alvo,
        ator=ator,
    )


def redefinir_senha(
    session: Session,
    *,
    ator: Usuario | None,
    alvo: Usuario,
    senha: str,
    must_change_password: bool = True,
) -> None:
    _nao_em_si_mesmo(ator, alvo)
    alvo.password_hash = gerar_hash_senha(senha)
    alvo.password_changed_at = datetime.now(UTC)
    alvo.must_change_password = must_change_password
    session.flush()
    registrar_evento(
        session,
        TipoEventoAuditoria.SENHA_REDEFINIDA,
        alvo=alvo,
        ator=ator,
        detalhes={"exigir_troca": must_change_password},
    )


def definir_modulos(
    session: Session, *, ator: Usuario | None, alvo: Usuario, modulos: Iterable[str]
) -> None:
    desejados = validar_modulos(alvo.role, modulos)
    antes = modulos_configurados(session, alvo)
    _aplicar_modulos(session, alvo, desejados)
    _auditar_modulos(session, ator=ator, alvo=alvo, antes=antes, origem=OrigemAuditoria.API)


def atualizar_usuario(
    session: Session,
    *,
    ator: Usuario | None,
    alvo: Usuario,
    nome_exibicao: str | None = None,
    role: str | None = None,
    ativo: bool | None = None,
    modulos: Iterable[str] | None = None,
    sessao_continua: bool | None = None,
) -> None:

    novo_nome = normalizar_nome_exibicao(nome_exibicao) if nome_exibicao is not None else None
    novo_role = validar_role(role) if role is not None else None
    role_final = novo_role or alvo.role
    desejados = validar_modulos(role_final, modulos) if modulos is not None else None
    sessao_final = alvo.sessao_continua if sessao_continua is None else sessao_continua
    validar_sessao_continua(role_final, sessao_final)

    muda_role = novo_role is not None and novo_role != alvo.role
    desativa = ativo is False and alvo.ativo
    sai_de_admin = _eh_admin(alvo) and (desativa or (muda_role and novo_role != PAPEL_ADMIN))
    if sai_de_admin:
        _proteger_saida_de_admin(session, ator, alvo)
    elif muda_role:
        _nao_em_si_mesmo(ator, alvo)

    antes = modulos_configurados(session, alvo)

    if novo_nome is not None and novo_nome != alvo.nome_exibicao:
        anterior = alvo.nome_exibicao
        alvo.nome_exibicao = novo_nome
        session.flush()
        registrar_evento(
            session,
            TipoEventoAuditoria.USUARIO_EDITADO,
            alvo=alvo,
            ator=ator,
            detalhes={
                "campos": ["nome_exibicao"],
                "nome_anterior": anterior,
                "nome_novo": novo_nome,
            },
        )

    if sessao_continua is not None and sessao_continua != alvo.sessao_continua:
        alvo.sessao_continua = sessao_continua
        session.flush()
        registrar_evento(
            session,
            TipoEventoAuditoria.USUARIO_EDITADO,
            alvo=alvo,
            ator=ator,
            detalhes={"campos": ["sessao_continua"], "sessao_continua": sessao_continua},
        )

    if muda_role and novo_role is not None:
        anterior = alvo.role
        alvo.role = novo_role
        session.flush()
        if novo_role == PAPEL_ADMIN:
            aplicar_permissoes_iniciais(session, alvo)
        else:
            revogar_permissao(session, alvo, Modulo.ADMINISTRACAO)
        registrar_evento(
            session,
            TipoEventoAuditoria.ROLE_ALTERADA,
            alvo=alvo,
            ator=ator,
            detalhes={"role_anterior": anterior, "role_nova": novo_role},
        )

    if desejados is not None:
        _aplicar_modulos(session, alvo, desejados)
    _auditar_modulos(session, ator=ator, alvo=alvo, antes=antes, origem=OrigemAuditoria.API)

    if ativo is not None:
        if alvo.ativo != ativo:
            alvo.ativo = ativo
            session.flush()
            registrar_evento(
                session,
                TipoEventoAuditoria.USUARIO_ATIVADO
                if ativo
                else TipoEventoAuditoria.USUARIO_DESATIVADO,
                alvo=alvo,
                ator=ator,
            )
