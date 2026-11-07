from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray

from app.anomalias.registros import RegistroTransferencia

Matriz = NDArray[np.float64]

FEATURES = (
    "valor_na_rota",
    "valor_por_item_na_rota",
    "transito_na_rota",
    "divergencia",
    "raridade_hora",
    "raridade_dia",
    "raridade_rota",
)


_ENCOLHIMENTO = 20.0

_DISPERSAO_MINIMA = 0.05

_FATOR_MAD = 1.4826

_SUAVIZACAO = 1.0
_QUANTIL_TOLERANCIA_DIVERGENCIA = 0.99


_FATIA_RARA = 0.05


@dataclass(frozen=True)
class Padrao:
    centro: float
    dispersao: float

    def desvio(self, valor_log: float) -> float:
        return (valor_log - self.centro) / self.dispersao

    def mediana(self) -> float:
        return float(np.exp(self.centro))


def _padrao(valores: Sequence[float]) -> Padrao:
    if not valores:
        return Padrao(0.0, 1.0)
    arr = np.asarray(valores, dtype=np.float64)
    centro = float(np.median(arr))
    mad = float(np.median(np.abs(arr - centro))) * _FATOR_MAD
    return Padrao(centro, max(mad, _DISPERSAO_MINIMA))


def _encolher(rota: Sequence[float], geral: Padrao) -> Padrao:
    if not rota:
        return geral
    proprio = _padrao(rota)
    peso = len(rota) / (len(rota) + _ENCOLHIMENTO)
    return Padrao(
        peso * proprio.centro + (1 - peso) * geral.centro,
        peso * proprio.dispersao + (1 - peso) * geral.dispersao,
    )


def _log_seguro(valor: float) -> float:
    return float(np.log(max(valor, 0.01)))


def horas_transito(r: RegistroTransferencia) -> float | None:
    if r.recebida_em is None:
        return None
    return max((r.recebida_em - r.emitida_em).total_seconds() / 3600, 0.0)


def divergencia(r: RegistroTransferencia) -> float:
    if r.quantidade_recebida is None or r.quantidade_enviada <= 0:
        return 0.0
    return abs(r.quantidade_enviada - r.quantidade_recebida) / r.quantidade_enviada


def _valor_por_item(r: RegistroTransferencia) -> float:
    return r.valor / max(r.quantidade_itens, 1)


class _Frequencias:
    def __init__(self, valores: Iterable[object], categorias_possiveis: int) -> None:
        self._contagem = Counter(valores)
        self._total = sum(self._contagem.values())
        self._categorias = categorias_possiveis

    def probabilidade(self, valor: object) -> float:
        return (self._contagem[valor] + _SUAVIZACAO) / (
            self._total + _SUAVIZACAO * self._categorias
        )

    def raridade(self, valor: object) -> float:
        return max(-float(np.log(self.probabilidade(valor) / _FATIA_RARA)), 0.0)


@dataclass(frozen=True)
class PadraoRota:
    valor: Padrao
    valor_por_item: Padrao
    transito: Padrao


class ExtratorFeatures:
    def __init__(self) -> None:
        self._rotas: dict[tuple[str, str], PadraoRota] = {}
        self._geral: PadraoRota | None = None
        self._horas: _Frequencias | None = None
        self._dias: _Frequencias | None = None
        self._freq_rotas: _Frequencias | None = None
        self.tolerancia_divergencia = 0.0

    def ajustar(self, registros: Sequence[RegistroTransferencia]) -> "ExtratorFeatures":
        if not registros:
            raise ValueError("sem transferencias para aprender o padrao")

        def valores(r: RegistroTransferencia) -> tuple[float, float]:
            return (_log_seguro(r.valor), _log_seguro(_valor_por_item(r)))

        def transitos(rs: Iterable[RegistroTransferencia]) -> list[float]:
            horas = (horas_transito(r) for r in rs)
            return [_log_seguro(h) for h in horas if h is not None]

        geral = PadraoRota(
            valor=_padrao([valores(r)[0] for r in registros]),
            valor_por_item=_padrao([valores(r)[1] for r in registros]),
            transito=_padrao(transitos(registros)),
        )
        por_rota: dict[tuple[str, str], list[RegistroTransferencia]] = {}
        for r in registros:
            por_rota.setdefault(r.rota, []).append(r)
        self._rotas = {
            rota: PadraoRota(
                valor=_encolher([valores(r)[0] for r in rs], geral.valor),
                valor_por_item=_encolher([valores(r)[1] for r in rs], geral.valor_por_item),
                transito=_encolher(transitos(rs), geral.transito),
            )
            for rota, rs in por_rota.items()
        }
        self._geral = geral
        self.tolerancia_divergencia = float(
            np.quantile([divergencia(r) for r in registros], _QUANTIL_TOLERANCIA_DIVERGENCIA)
        )
        self._horas = _Frequencias((r.emitida_em.hour for r in registros), 24)
        self._dias = _Frequencias((r.emitida_em.weekday() for r in registros), 7)
        empresas = {e for r in registros for e in r.rota}
        self._freq_rotas = _Frequencias(
            (r.rota for r in registros), max(len(empresas) * (len(empresas) - 1), 1)
        )
        return self

    def padrao_rota(self, rota: tuple[str, str]) -> PadraoRota:
        if self._geral is None:
            raise RuntimeError("extrator ainda nao ajustado")
        return self._rotas.get(rota, self._geral)

    def probabilidade_hora(self, emitida_em: datetime) -> float:
        assert self._horas is not None
        return self._horas.probabilidade(emitida_em.hour)

    def probabilidade_dia(self, emitida_em: datetime) -> float:
        assert self._dias is not None
        return self._dias.probabilidade(emitida_em.weekday())

    def probabilidade_rota(self, rota: tuple[str, str]) -> float:
        assert self._freq_rotas is not None
        return self._freq_rotas.probabilidade(rota)

    def transformar(self, registros: Sequence[RegistroTransferencia]) -> Matriz:
        if self._horas is None or self._dias is None or self._freq_rotas is None:
            raise RuntimeError("extrator ainda nao ajustado")
        linhas: list[list[float]] = []
        for r in registros:
            p = self.padrao_rota(r.rota)
            horas = horas_transito(r)
            linhas.append(
                [
                    p.valor.desvio(_log_seguro(r.valor)),
                    p.valor_por_item.desvio(_log_seguro(_valor_por_item(r))),
                    0.0 if horas is None else p.transito.desvio(_log_seguro(horas)),
                    max(divergencia(r) - self.tolerancia_divergencia, 0.0),
                    self._horas.raridade(r.emitida_em.hour),
                    self._dias.raridade(r.emitida_em.weekday()),
                    self._freq_rotas.raridade(r.rota),
                ]
            )
        return np.asarray(linhas, dtype=np.float64).reshape(-1, len(FEATURES))
