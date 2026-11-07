from dataclasses import dataclass
from datetime import timedelta

STATUS_PROCESSADA = "PROCESSADA"
STATUS_PENDENTE = "PENDENTE"
STATUS_ERRO = "ERRO"
STATUS_CANCELADA = "CANCELADA"

LIMITE_MAXIMO_HORAS = 720


@dataclass(frozen=True)
class Limites:
    horas_atencao: int = 24
    horas_critico: int = 48

    @property
    def atencao(self) -> timedelta:
        return timedelta(hours=self.horas_atencao)

    @property
    def critico(self) -> timedelta:
        return timedelta(hours=self.horas_critico)


LIMITES_PADRAO = Limites()
