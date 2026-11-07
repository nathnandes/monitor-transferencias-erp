import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.dominio.intervalo import Intervalo
from app.notifications.modelos import Variavel, renderizar
from app.services.financeiro import resumo_financeiro
from app.services.vendas import Totais, cobertura, totais_do_periodo

_VARIAVEL = re.compile(r"\{(\w+)\}")


class VariavelDesconhecida(ValueError):
    pass


VARIAVEIS: tuple[Variavel, ...] = (
    Variavel("data", "Data do envio", "05/11/2026"),
    Variavel("hora", "Hora do envio", "18:00"),
    Variavel("faturamento", "Faturamento bruto de hoje", "R$ 48.210,90"),
    Variavel("faturamento_liquido", "Faturamento líquido de hoje", "R$ 47.890,90"),
    Variavel("devolucoes", "Devoluções de hoje", "R$ 320,00"),
    Variavel("notas", "Notas de venda de hoje", "312"),
    Variavel("ticket_medio", "Ticket médio de hoje", "R$ 154,52"),
    Variavel("recebido", "Recebido hoje", "R$ 31.540,00"),
    Variavel("faturamento_liquido_ontem", "Faturamento líquido de ontem", "R$ 52.100,00"),
    Variavel("recebido_ontem", "Recebido ontem", "R$ 29.870,00"),
    Variavel("faturamento_liquido_mes", "Faturamento líquido do mês até hoje", "R$ 412.300,00"),
    Variavel("recebido_mes", "Recebido no mês até hoje", "R$ 288.900,00"),
    Variavel("atualizado_em", "Última sincronização das vendas", "05/11 17:55"),
)
CHAVES = frozenset(v.chave for v in VARIAVEIS)


def moeda(valor: Decimal) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def usadas(texto: str) -> set[str]:
    return set(_VARIAVEL.findall(texto))


def validar(texto: str) -> None:
    desconhecidas = sorted(usadas(texto) - CHAVES)
    if desconhecidas:
        lista = ", ".join(f"{{{v}}}" for v in desconhecidas)
        raise VariavelDesconhecida(f"Variável que não existe: {lista}.")


def _calculadoras(db: Session, agora: datetime, tz: ZoneInfo) -> dict[str, Callable[[], str]]:
    local = agora.astimezone(tz)
    hoje: date = local.date()
    ontem = hoje - timedelta(days=1)
    periodos = {
        "": Intervalo(hoje, hoje),
        "_ontem": Intervalo(ontem, ontem),
        "_mes": Intervalo(hoje.replace(day=1), hoje),
    }
    totais: dict[str, Totais] = {}
    recebidos: dict[str, Decimal] = {}

    def vendas(sufixo: str) -> Totais:
        if sufixo not in totais:
            totais[sufixo] = totais_do_periodo(db, periodos[sufixo])
        return totais[sufixo]

    def recebido(sufixo: str) -> Decimal:
        if sufixo not in recebidos:
            recebidos[sufixo] = resumo_financeiro(db, None, periodos[sufixo]).recebidos.total
        return recebidos[sufixo]

    def atualizado_em() -> str:
        momento = cobertura(db).atualizado_em
        return f"{momento.astimezone(tz):%d/%m %H:%M}" if momento else "sem sincronização"

    def ticket() -> str:
        valor = vendas("").ticket_medio
        return moeda(valor) if valor is not None else moeda(Decimal(0))

    return {
        "data": lambda: f"{local:%d/%m/%Y}",
        "hora": lambda: f"{local:%H:%M}",
        "faturamento": lambda: moeda(vendas("").faturamento),
        "faturamento_liquido": lambda: moeda(vendas("").liquido),
        "devolucoes": lambda: moeda(vendas("").devolucoes or Decimal(0)),
        "notas": lambda: str(vendas("").notas),
        "ticket_medio": ticket,
        "recebido": lambda: moeda(recebido("")),
        "faturamento_liquido_ontem": lambda: moeda(vendas("_ontem").liquido),
        "recebido_ontem": lambda: moeda(recebido("_ontem")),
        "faturamento_liquido_mes": lambda: moeda(vendas("_mes").liquido),
        "recebido_mes": lambda: moeda(recebido("_mes")),
        "atualizado_em": atualizado_em,
    }


def preencher(db: Session, texto: str, agora: datetime, tz: ZoneInfo) -> str:
    chaves = usadas(texto) & CHAVES
    if not chaves:
        return texto
    calculadoras = _calculadoras(db, agora, tz)
    return renderizar(texto, {chave: calculadoras[chave]() for chave in chaves})
