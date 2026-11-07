from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement


class IntervaloInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Intervalo:
    inicio: date
    fim: date

    def __post_init__(self) -> None:
        if self.inicio > self.fim:
            raise IntervaloInvalido(f"Início ({self.inicio}) posterior ao fim ({self.fim}).")

    def condicao(self, coluna: Any, tz: ZoneInfo) -> ColumnElement[bool]:
        inicio = datetime.combine(self.inicio, time.min, tzinfo=tz)
        fim = datetime.combine(self.fim + timedelta(days=1), time.min, tzinfo=tz)
        dentro: ColumnElement[bool] = (coluna >= inicio) & (coluna < fim)
        return dentro
