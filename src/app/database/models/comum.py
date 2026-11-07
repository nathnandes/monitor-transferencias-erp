from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.dominio.modulos import Modulo

STATUS_SINCRONIZACAO = ("em_andamento", "sucesso", "parcial", "erro")
SEVERIDADES_EVENTO = ("INFO", "WARNING", "ERROR", "CRITICAL")
NIVEIS_LOG = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
PAPEIS_USUARIO = ("ADMIN", "OPERADOR")

MODULOS_SISTEMA = tuple(m.value for m in Modulo)


TIPOS_EVENTO_AUDITORIA = (
    "USUARIO_CRIADO",
    "USUARIO_EDITADO",
    "USUARIO_ATIVADO",
    "USUARIO_DESATIVADO",
    "SENHA_REDEFINIDA",
    "ROLE_ALTERADA",
    "PERMISSOES_ALTERADAS",
)

ORIGENS_AUDITORIA = ("API", "CLI")


STATUS_ALERTA = ("ABERTO", "RESOLVIDO")
CANAIS_NOTIFICACAO = ("telegram", "whatsapp")


TIPOS_NOTIFICACAO = ("ABERTURA", "ESCALADA", "RESOLUCAO", "ATIVIDADE", "MENSAGEM")

STATUS_NOTIFICACAO = ("PENDENTE", "ENVIADA", "FALHA", "DESCARTADA")

STATUS_RESUMO_DIARIO = ("PENDENTE", "ENVIADO", "FALHA")


TIPOS_SINCRONIZACAO_MANUAL = (
    "empresas",
    "estoque",
    "estoque_completo",
    "transferencias",
    "precos",
    "precos_completo",
    "vendas",
    "movimentos_estoque",
)
STATUS_SOLICITACAO_SINCRONIZACAO = ("PENDENTE", "EM_EXECUCAO", "CONCLUIDA")


USERNAME_REGEX_SQL = "^[a-z0-9._-]{3,50}$"


def _in(coluna: str, valores: tuple[str, ...]) -> str:
    return f"{coluna} IN ({', '.join(repr(v) for v in valores)})"


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def _jsonb() -> Mapped[dict[str, Any]]:
    return mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
