from dataclasses import dataclass, field
from typing import Literal

TipoCoi = Literal["SAIDA", "ENTRADA"]


COIS_SAIDA: dict[int, frozenset[int]] = {
    1: frozenset({8040}),
    2: frozenset({8044}),
    3: frozenset({8051}),
    4: frozenset({8039}),
    5: frozenset({8052}),
    6: frozenset({8061}),
}


COI_ENTRADA: dict[int, int] = {
    1: 51,
    2: 7162,
    3: 7161,
    4: 7163,
    5: 7164,
    6: 7661,
}


COI_ENTRADA_EXCECOES: dict[tuple[int, int], int] = {
    (6, 1): 7661,
}


COIS_FISCAIS: frozenset[int] = frozenset({8060})

EMPRESAS: frozenset[int] = frozenset(COI_ENTRADA)

_COIS_SAIDA_TODOS = frozenset(c for cois in COIS_SAIDA.values() for c in cois)
_COIS_ENTRADA_TODOS = frozenset(COI_ENTRADA.values()) | frozenset(COI_ENTRADA_EXCECOES.values())


def tipo(coi: int | None) -> TipoCoi | None:
    if coi in _COIS_SAIDA_TODOS:
        return "SAIDA"
    if coi in _COIS_ENTRADA_TODOS:
        return "ENTRADA"
    return None


def coi_entrada_esperado(empresa_origem: int | None, empresa_destino: int) -> int | None:
    if empresa_origem is not None:
        excecao = COI_ENTRADA_EXCECOES.get((empresa_origem, empresa_destino))
        if excecao is not None:
            return excecao
    return COI_ENTRADA.get(empresa_destino)


def problemas_saida(empresa_origem: int, coi: int, empresa_destino: int | None) -> list[str]:
    problemas: list[str] = []
    esperados = COIS_SAIDA.get(empresa_origem, frozenset())
    if coi not in esperados:
        certos = ", ".join(str(c) for c in sorted(esperados)) or "nenhum"
        problemas.append(
            f"COI de saida {coi} nao e da empresa {empresa_origem} (esperado: {certos})"
        )
    if empresa_destino is None or empresa_destino not in EMPRESAS:
        problemas.append("destino da nota nao e uma das 6 empresas")
    elif empresa_destino == empresa_origem:
        problemas.append("destino da nota e a propria empresa de origem")
    return problemas


def problemas_entrada(empresa_destino: int, coi: int, empresa_origem: int | None) -> list[str]:
    problemas: list[str] = []
    esperado = coi_entrada_esperado(empresa_origem, empresa_destino)
    if coi != esperado:
        problemas.append(
            f"COI de entrada {coi} nao e o da empresa {empresa_destino} (esperado: {esperado})"
        )
    if empresa_origem is None or empresa_origem not in EMPRESAS:
        problemas.append("origem da nota nao e uma das 6 empresas")
    elif empresa_origem == empresa_destino:
        problemas.append("origem da nota e a propria empresa de destino")
    return problemas


def _numero(valor: str | int | None) -> int | None:
    if valor is None:
        return None
    try:
        return int(str(valor).strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class Conferencia:
    problemas: list[str] = field(default_factory=list)
    fora_do_padrao: list[str] = field(default_factory=list)

    @property
    def entre_empresas(self) -> bool:

        return bool(self.problemas) or not self.fora_do_padrao


def conferir_transferencia(
    *,
    origem: str | None,
    coi_saida: str | None,
    destino: str | None,
    coi_entrada: str | None = None,
    empresa_entrada: str | None = None,
    origem_da_entrada: str | None = None,
    entrada_registrada: bool = False,
) -> Conferencia:
    problemas: list[str] = []
    coi_saida_n = _numero(coi_saida)
    coi_entrada_n = _numero(coi_entrada)
    if coi_saida_n is None:
        problemas.append("nota de saida sem COI")
    if entrada_registrada and coi_entrada_n is None:
        problemas.append("nota de entrada sem COI")
    return Conferencia(
        problemas,
        _fora_do_padrao(
            origem=origem,
            coi_saida=coi_saida_n,
            destino=destino,
            coi_entrada=coi_entrada_n,
            empresa_entrada=empresa_entrada,
            origem_da_entrada=origem_da_entrada,
        ),
    )


def _fora_do_padrao(
    *,
    origem: str | None,
    coi_saida: int | None,
    destino: str | None,
    coi_entrada: int | None,
    empresa_entrada: str | None,
    origem_da_entrada: str | None,
) -> list[str]:
    origem_n = _numero(origem)
    destino_n = _numero(destino)
    problemas: list[str] = []
    if origem_n is None:
        problemas.append("nota de saida sem empresa")
    elif coi_saida is not None:
        problemas += problemas_saida(origem_n, coi_saida, destino_n)

    if coi_entrada is None:
        return problemas
    entrada_n = _numero(empresa_entrada)
    if entrada_n is None:
        return [*problemas, "nota de entrada sem empresa"]
    if destino_n is not None and entrada_n != destino_n:
        problemas.append(
            f"entrada registrada na empresa {entrada_n}, mas a nota foi para a {destino_n}"
        )
    remetente = _numero(origem_da_entrada)
    for problema in problemas_entrada(
        entrada_n, coi_entrada, remetente if remetente is not None else origem_n
    ):
        if problema not in problemas:
            problemas.append(problema)
    return problemas
