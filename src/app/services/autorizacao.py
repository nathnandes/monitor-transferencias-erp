from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import PermissaoModulo, Usuario
from app.dominio.modulos import Modulo
from app.services.perfis import Acesso, abas_do_perfil, modulos_do_perfil

PAPEL_ADMIN = "ADMIN"
PERMISSOES_INICIAIS_ADMIN = (Modulo.ADMINISTRACAO, Modulo.DASHBOARD)


class PermissaoInvalidaError(ValueError):
    pass


def validar_modulo(valor: str) -> Modulo:
    try:
        return Modulo(valor)
    except ValueError:
        raise PermissaoInvalidaError(f"modulo deve ser um de: {', '.join(Modulo)}") from None


def _eh_admin(usuario: Usuario) -> bool:
    return usuario.role == PAPEL_ADMIN


def conceder_permissao(session: Session, usuario: Usuario, modulo: str) -> None:
    modulo = validar_modulo(modulo)
    if modulo is Modulo.ADMINISTRACAO and not _eh_admin(usuario):
        raise PermissaoInvalidaError("ADMINISTRACAO so pode ser atribuida a ADMIN")

    comando = insert(PermissaoModulo).values(user_id=usuario.id, module=modulo, can_view=True)
    session.execute(
        comando.on_conflict_do_update(
            constraint="uq_user_module_permissions_user_module",
            set_={"can_view": True, "updated_at": func.now()},
        )
    )
    session.flush()


def revogar_permissao(session: Session, usuario: Usuario, modulo: str) -> None:
    modulo = validar_modulo(modulo)
    if modulo is Modulo.ADMINISTRACAO and _eh_admin(usuario):
        raise PermissaoInvalidaError("ADMIN sempre possui ADMINISTRACAO")

    permissao = session.scalar(
        select(PermissaoModulo).where(
            PermissaoModulo.user_id == usuario.id, PermissaoModulo.module == modulo
        )
    )
    if permissao is not None:
        permissao.can_view = False
        session.flush()


def aplicar_permissoes_iniciais(session: Session, usuario: Usuario) -> None:
    if _eh_admin(usuario):
        for modulo in PERMISSOES_INICIAIS_ADMIN:
            conceder_permissao(session, usuario, modulo)


def permissoes_efetivas(session: Session, usuario: Usuario) -> frozenset[Modulo]:
    if not usuario.ativo:
        return frozenset()
    if usuario.perfil is not None:
        modulos = set(modulos_do_perfil(usuario.perfil))
        if _eh_admin(usuario):
            modulos.add(Modulo.ADMINISTRACAO)
        return frozenset(modulos)
    return modulos_configurados(session, usuario)


def acesso_efetivo(session: Session, usuario: Usuario) -> Acesso:
    modulos = permissoes_efetivas(session, usuario)
    perfil = usuario.perfil
    if perfil is None or not modulos:
        return Acesso(modulos=modulos, abas=None, tela_inicial=None)
    return Acesso(modulos=modulos, abas=abas_do_perfil(perfil), tela_inicial=perfil.tela_inicial)


def modulos_configurados(session: Session, usuario: Usuario) -> frozenset[Modulo]:
    liberados = {
        Modulo(m)
        for m in session.scalars(
            select(PermissaoModulo.module).where(
                PermissaoModulo.user_id == usuario.id, PermissaoModulo.can_view.is_(True)
            )
        )
    }
    if _eh_admin(usuario):
        liberados.add(Modulo.ADMINISTRACAO)
    else:
        liberados.discard(Modulo.ADMINISTRACAO)
    return frozenset(liberados)


def tem_permissao(session: Session, usuario: Usuario, modulo: str) -> bool:
    return validar_modulo(modulo) in permissoes_efetivas(session, usuario)


def ordenar(modulos: frozenset[Modulo]) -> list[Modulo]:
    return [m for m in Modulo if m in modulos]
