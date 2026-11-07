from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from app.anomalias.features import FEATURES, ExtratorFeatures, Matriz, divergencia, horas_transito
from app.anomalias.registros import RegistroTransferencia

_DIAS_SEMANA = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

_CONTRIBUICAO_MINIMA = 0.005

_FRACAO_DO_PRINCIPAL = 0.25
_MAXIMO_MOTIVOS = 3


@dataclass(frozen=True)
class Motivo:
    feature: str
    contribuicao: float
    texto: str


@dataclass(frozen=True)
class Resultado:
    registro: RegistroTransferencia
    score: float
    sinalizada: bool
    motivos: tuple[Motivo, ...] = ()


def _vezes(razao: float) -> str:
    return f"{razao:.1f}".replace(".", ",") + "x"


def _percentual(fracao: float) -> str:
    if fracao < 0.001:
        return "menos de 0,1%"
    casas = 1 if fracao < 0.1 else 0
    return f"{fracao * 100:.{casas}f}".replace(".", ",") + "%"


def _moeda(valor: float) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


class DetectorAnomalias:
    def __init__(
        self,
        *,
        n_estimators: int = 300,
        max_samples: int = 512,
        fracao_alerta: float = 0.02,
        semente: int = 42,
    ) -> None:
        if not 0 < fracao_alerta < 1:
            raise ValueError("fracao_alerta precisa estar entre 0 e 1")
        self.fracao_alerta = fracao_alerta
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.extrator = ExtratorFeatures()
        self._floresta: Any = IsolationForest(
            n_estimators=n_estimators,
            max_samples=max_samples,
            contamination="auto",
            random_state=semente,
        )
        self._tipicos: Matriz | None = None
        self.limiar: float | None = None

    def treinar(self, registros: Sequence[RegistroTransferencia]) -> "DetectorAnomalias":
        matriz = self.extrator.ajustar(registros).transformar(registros)
        self._floresta.set_params(max_samples=min(self._floresta.max_samples, len(registros)))
        self._floresta.fit(matriz)
        self._tipicos = np.median(matriz, axis=0)
        self.limiar = float(np.quantile(self._scores(matriz), 1 - self.fracao_alerta))
        return self

    def _scores(self, matriz: Matriz) -> Matriz:

        return -np.asarray(self._floresta.score_samples(matriz), dtype=np.float64)

    def pontuar(self, registros: Sequence[RegistroTransferencia]) -> Matriz:
        if self.limiar is None:
            raise RuntimeError("detector ainda nao treinado")
        if not registros:
            return np.empty(0, dtype=np.float64)
        return self._scores(self.extrator.transformar(registros))

    def contribuicoes(self, registro: RegistroTransferencia) -> dict[str, float]:
        if self._tipicos is None:
            raise RuntimeError("detector ainda nao treinado")
        linha = self.extrator.transformar([registro])
        alteradas = np.repeat(linha, len(FEATURES), axis=0)
        np.fill_diagonal(alteradas, self._tipicos)
        original = self._scores(linha)[0]
        return {
            nome: float(original - score)
            for nome, score in zip(FEATURES, self._scores(alteradas), strict=True)
        }

    def analisar(self, registros: Sequence[RegistroTransferencia]) -> list[Resultado]:
        scores = self.pontuar(registros)
        assert self.limiar is not None
        resultados = []
        for registro, score in zip(registros, scores, strict=True):
            sinalizada = bool(score >= self.limiar)
            motivos = self.explicar(registro) if sinalizada else ()
            resultados.append(Resultado(registro, float(score), sinalizada, motivos))
        return resultados

    def explicar(self, registro: RegistroTransferencia) -> tuple[Motivo, ...]:
        ordenadas = sorted(self.contribuicoes(registro).items(), key=lambda c: c[1], reverse=True)
        corte = max(_CONTRIBUICAO_MINIMA, ordenadas[0][1] * _FRACAO_DO_PRINCIPAL)
        motivos: list[Motivo] = []
        for nome, contribuicao in ordenadas:
            if contribuicao < corte or len(motivos) == _MAXIMO_MOTIVOS:
                break
            texto = self._texto(nome, registro)
            if texto:
                motivos.append(Motivo(nome, contribuicao, texto))
        if not motivos:
            return (Motivo("conjunto", 0.0, "combinação incomum de fatores, nenhum isolado"),)
        return tuple(motivos)

    def _texto(self, feature: str, r: RegistroTransferencia) -> str | None:
        padrao = self.extrator.padrao_rota(r.rota)
        if feature == "valor_na_rota":
            mediana = padrao.valor.mediana()
            return (
                f"valor de {_moeda(r.valor)}, {_vezes(r.valor / mediana)} "
                f"a mediana da rota ({_moeda(mediana)})"
            )
        if feature == "valor_por_item_na_rota":
            por_item = r.valor / max(r.quantidade_itens, 1)
            mediana = padrao.valor_por_item.mediana()
            return f"{_moeda(por_item)} por item, {_vezes(por_item / mediana)} o normal da rota"
        if feature == "transito_na_rota":
            horas = horas_transito(r)
            if horas is None:
                return None
            mediana = padrao.transito.mediana()
            return (
                f"{horas:.0f}h até a entrada, {_vezes(horas / mediana)} "
                f"o normal da rota ({mediana:.0f}h)"
            )
        if feature == "divergencia":
            enviada, recebida = r.quantidade_enviada, r.quantidade_recebida
            if recebida is None or divergencia(r) == 0:
                return None
            verbo = "faltaram" if recebida < enviada else "sobraram"
            return f"{verbo} {_percentual(divergencia(r))} da quantidade enviada"
        if feature == "raridade_hora":
            p = self.extrator.probabilidade_hora(r.emitida_em)
            return f"emitida às {r.emitida_em.hour}h, horário de {_percentual(p)} das notas"
        if feature == "raridade_dia":
            p = self.extrator.probabilidade_dia(r.emitida_em)
            dia = _DIAS_SEMANA[r.emitida_em.weekday()]
            return f"emitida em {dia}, dia de {_percentual(p)} das notas"
        if feature == "raridade_rota":
            p = self.extrator.probabilidade_rota(r.rota)
            return f"rota rara: {r.origem} → {r.destino}, {_percentual(p)} das notas"
        raise ValueError(f"feature desconhecida: {feature}")
