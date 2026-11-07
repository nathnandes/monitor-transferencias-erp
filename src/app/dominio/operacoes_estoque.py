from dataclasses import dataclass
from typing import Literal

Categoria = Literal[
    "venda",
    "devolucao_venda",
    "compra",
    "devolucao_compra",
    "transferencia_entrada",
    "transferencia_saida",
    "entrada_avulsa",
    "saida_avulsa",
    "balanco",
    "perda",
    "uso_consumo",
    "producao",
    "bonificacao",
    "remessa",
    "outros",
    "nao_classificado",
]

CATEGORIAS: tuple[Categoria, ...] = (
    "venda",
    "devolucao_venda",
    "compra",
    "devolucao_compra",
    "transferencia_entrada",
    "transferencia_saida",
    "entrada_avulsa",
    "saida_avulsa",
    "balanco",
    "perda",
    "uso_consumo",
    "producao",
    "bonificacao",
    "remessa",
    "outros",
    "nao_classificado",
)

COI_BALANCO = 2000


VERSAO_LIVRO = 2


@dataclass(frozen=True)
class Operacao:
    coi: int
    saida: bool
    categoria: Categoria
    afeta: bool | None

    @property
    def fator(self) -> int:
        if self.coi == COI_BALANCO:
            return 1
        return -1 if self.saida else 1


def _ops(saida: bool, categoria: Categoria, afeta: bool | None, *cois: int) -> list[Operacao]:
    return [Operacao(c, saida, categoria, afeta) for c in cois]


S, E = True, False

_CATALOGO: list[Operacao] = [
    *_ops(S, "venda", True, 8001, 8003, 8300, 3001),
    *_ops(S, "venda", False, 8301),
    *_ops(S, "venda", False, 3000),
    *_ops(S, "venda", None, 8090, 8095, 8153),
    *_ops(S, "outros", False, 8007),
    *_ops(S, "devolucao_compra", True, 8030),
    *_ops(S, "devolucao_compra", None, 8035),
    *_ops(S, "uso_consumo", True, 8037, 8038, 8041),
    *_ops(
        S,
        "transferencia_saida",
        True,
        8039,
        8040,
        8043,
        8044,
        8045,
        8050,
        8051,
        8052,
        8053,
        8054,
        8055,
        8058,
        8060,
        8061,
        8088,
    ),
    *_ops(S, "saida_avulsa", True, 8080),
    *_ops(S, "producao", True, 8081, 8087),
    *_ops(S, "perda", True, 8082),
    *_ops(S, "bonificacao", True, 8122),
    *_ops(S, "remessa", None, 8121, 8124),
    *_ops(S, "outros", None, 8302),
    *_ops(S, "balanco", True, COI_BALANCO),
    *_ops(E, "compra", True, 1, 8, 9, 10, 11),
    *_ops(E, "compra", None, 12, 13, 45, 46),
    *_ops(E, "devolucao_venda", True, 30, 31),
    *_ops(
        E,
        "transferencia_entrada",
        True,
        51,
        85,
        88,
        7156,
        7158,
        7161,
        7162,
        7163,
        7164,
        7661,
    ),
    *_ops(E, "entrada_avulsa", True, 80),
    *_ops(E, "producao", True, 81),
    *_ops(E, "bonificacao", True, 7171),
    *_ops(E, "uso_consumo", None, 3, 7203, 7204, 7205, 7207, 7212, 7213, 7214),
    *_ops(E, "remessa", None, 4, 5),
    *_ops(E, "remessa", False, 20, 7120),
    *_ops(E, "outros", False, 94, 7140, 7206, 7208, 7209, 7210),
    *_ops(E, "outros", False, 7472),
]

CATALOGO: dict[tuple[bool, int], Operacao] = {(o.saida, o.coi): o for o in _CATALOGO}


def operacao(saida: bool, coi: int) -> Operacao:
    return CATALOGO.get((saida, coi)) or Operacao(coi, saida, "nao_classificado", None)


def cois_que_afetam() -> list[int]:
    return sorted({o.coi for o in _CATALOGO if o.afeta})
