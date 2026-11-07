from typing import Literal

Canal = Literal["balcao", "televendas", "faturamento"]


CANAIS: dict[int, Canal] = {
    8300: "balcao",
    8001: "televendas",
    3001: "faturamento",
}

COIS_VENDA = tuple(sorted(CANAIS))


COIS_DEVOLUCAO = (30, 31)


SERIE_RECEBIMENTO_VENDA = "PDV"
