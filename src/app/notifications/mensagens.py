from datetime import datetime
from zoneinfo import ZoneInfo

from app.database.models import Alerta, Atividade
from app.notifications.modelos import (
    LIMITE_CARACTERES,
    PADRAO_ATIVIDADE,
    PADRAO_AVISO,
    PADRAO_RESOLUCAO,
    renderizar,
)
from app.rules.catalogo import montar_corpo

__all__ = ["LIMITE_CARACTERES", "corpo", "montar_texto", "montar_texto_atividade"]

_EMOJI = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}
_NIVEL = {"INFO": "informação", "WARNING": "atenção", "ERROR": "erro", "CRITICAL": "crítico"}


def _hora(momento: datetime, tz: ZoneInfo) -> str:
    return momento.astimezone(tz).strftime("%d/%m %H:%M")


def corpo(alerta: Alerta, campos: list[str] | None) -> str:
    valores = (alerta.detalhes or {}).get("campos")
    if campos is None or not isinstance(valores, dict):
        return alerta.mensagem
    return montar_corpo(alerta.regra, valores, campos)


def montar_texto(
    alerta: Alerta,
    tipo: str,
    tz: ZoneInfo,
    campos: list[str] | None = None,
    modelo: str | None = None,
) -> str:
    valores_campos = (alerta.detalhes or {}).get("campos")
    valores: dict[str, str] = dict(valores_campos) if isinstance(valores_campos, dict) else {}
    valores |= {
        "titulo": alerta.titulo,
        "desde": _hora(alerta.aberto_em, tz),
        "id": str(alerta.id),
    }
    if tipo == "RESOLUCAO":
        assert alerta.resolvido_em is not None
        valores["resolvido_em"] = _hora(alerta.resolvido_em, tz)
        return renderizar(modelo or PADRAO_RESOLUCAO, valores)

    valores |= {
        "emoji": _EMOJI.get(alerta.severidade, ""),
        "severidade": alerta.severidade,
        "nivel": _NIVEL.get(alerta.severidade, alerta.severidade),
        "agravou": "AGRAVOU PARA " if tipo == "ESCALADA" else "",
        "campos": corpo(alerta, campos),
    }
    return renderizar(modelo or PADRAO_AVISO, valores)


_EMOJI_ATIVIDADE = {
    "login": "👤",
    "logout": "👋",
    "login_recusado": "⛔",
    "meta_atingida": "🎯",
    "estoque_baixo": "📦",
}


def montar_texto_atividade(
    atividade: Atividade, tz: ZoneInfo, campos: list[str], modelo: str | None = None
) -> str:

    valores = {
        "usuario": atividade.usuario_nome,
        "quando": _hora(atividade.ocorrida_em, tz),
        "detalhe": atividade.detalhe or "",
        "ip": atividade.ip or "",
        **(atividade.valores or {}),
    }
    valores |= {
        "emoji": _EMOJI_ATIVIDADE.get(atividade.tipo, "✏️"),
        "titulo": atividade.resumo,
        "campos": montar_corpo(atividade.tipo, valores, campos),
    }
    return renderizar(modelo or PADRAO_ATIVIDADE, valores)
