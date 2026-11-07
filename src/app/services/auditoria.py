from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EventoAuditoriaUsuario, Usuario


class TipoEventoAuditoria(StrEnum):
    USUARIO_CRIADO = "USUARIO_CRIADO"
    USUARIO_EDITADO = "USUARIO_EDITADO"
    USUARIO_ATIVADO = "USUARIO_ATIVADO"
    USUARIO_DESATIVADO = "USUARIO_DESATIVADO"
    SENHA_REDEFINIDA = "SENHA_REDEFINIDA"
    ROLE_ALTERADA = "ROLE_ALTERADA"
    PERMISSOES_ALTERADAS = "PERMISSOES_ALTERADAS"


class OrigemAuditoria(StrEnum):
    API = "API"
    CLI = "CLI"


CHAVES_DETALHES = frozenset(
    {
        "campos",
        "nome_anterior",
        "nome_novo",
        "role",
        "role_anterior",
        "role_nova",
        "modulos",
        "modulos_concedidos",
        "modulos_revogados",
        "sessao_continua",
        "perfil_anterior",
        "perfil_novo",
        "exigir_troca",
    }
)


def _validar_detalhes(detalhes: dict[str, object]) -> dict[str, object]:
    proibidas = set(detalhes) - CHAVES_DETALHES
    if proibidas:
        raise ValueError(f"chave nao permitida na auditoria: {', '.join(sorted(proibidas))}")
    for chave, valor in detalhes.items():
        simples = isinstance(valor, str | bool) or (
            isinstance(valor, list) and all(isinstance(v, str) for v in valor)
        )
        if not simples:
            raise ValueError(f"valor nao permitido na auditoria: {chave}")
    return detalhes


def registrar_evento(
    session: Session,
    tipo: TipoEventoAuditoria,
    *,
    alvo: Usuario,
    ator: Usuario | None,
    origem: OrigemAuditoria = OrigemAuditoria.API,
    detalhes: dict[str, object] | None = None,
) -> EventoAuditoriaUsuario:
    evento = EventoAuditoriaUsuario(
        event_type=TipoEventoAuditoria(tipo),
        origem=OrigemAuditoria(origem),
        actor_user_id=ator.id if ator else None,
        actor_username=ator.username if ator else None,
        target_user_id=alvo.id,
        target_username=alvo.username,
        detalhes=_validar_detalhes(dict(detalhes or {})),
    )
    session.add(evento)
    session.flush()
    return evento


def eventos_do_usuario(session: Session, usuario_id: int) -> list[EventoAuditoriaUsuario]:
    return list(
        session.scalars(
            select(EventoAuditoriaUsuario)
            .where(EventoAuditoriaUsuario.target_user_id == usuario_id)
            .order_by(EventoAuditoriaUsuario.created_at, EventoAuditoriaUsuario.id)
        )
    )
