from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.autenticacao import UsuarioAutenticadoDep
from app.api.deps import SessionDep
from app.database.models import Usuario
from app.database.session import liberar_conexao
from app.dominio.modulos import Modulo
from app.services.autorizacao import PAPEL_ADMIN, permissoes_efetivas

MSG_SEM_PERMISSAO = "Sem permissão para acessar este recurso."


def sem_permissao() -> HTTPException:

    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MSG_SEM_PERMISSAO)


def get_permissoes(usuario: UsuarioAutenticadoDep, db: SessionDep) -> frozenset[Modulo]:
    permissoes = permissoes_efetivas(db, usuario)
    liberar_conexao(db)
    return permissoes


PermissoesDep = Annotated[frozenset[Modulo], Depends(get_permissoes)]


def exigir_admin(usuario: UsuarioAutenticadoDep) -> Usuario:
    if usuario.role != PAPEL_ADMIN:
        raise sem_permissao()
    return usuario


AdminDep = Annotated[Usuario, Depends(exigir_admin)]


def exigir_modulo(modulo: Modulo) -> Callable[..., None]:

    def _verificar(permissoes: PermissoesDep) -> None:
        if modulo not in permissoes:
            raise sem_permissao()

    _verificar.__name__ = f"exigir_modulo_{modulo.lower()}"
    return _verificar
