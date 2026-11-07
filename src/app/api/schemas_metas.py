from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Nivel = Literal["GRUPO", "EMPRESA", "VENDEDOR"]
Periodo = Literal["DIA", "SEMANA", "MES"]


class Meta(BaseModel):
    id: int
    nivel: Nivel
    empresa_id: int | None
    id_vendedor: str | None
    alvo: str = Field(description="Nome do alvo: o grupo, a loja ou o vendedor.")
    periodo: Periodo
    referencia: date | None = Field(
        description="Nula: vale sempre. Preenchida: só o período dela (dia, segunda ou dia 1)."
    )
    valor: Decimal
    atualizado_por: str
    atualizado_em: datetime


class MetaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nivel: Nivel
    periodo: Periodo
    valor: Decimal = Field(gt=0, max_digits=16, decimal_places=2, examples=["500000.00"])
    empresa_id: int | None = Field(default=None, description="Obrigatório no nível EMPRESA.")
    id_vendedor: str | None = Field(
        default=None, max_length=50, description="Obrigatório no nível VENDEDOR."
    )
    referencia: date | None = Field(
        default=None,
        description="Vazia: vale sempre. Uma data: só no dia, na semana ou no mês dela.",
    )


class Marcos(BaseModel):
    marcos: list[int] = Field(
        min_length=1, max_length=10, description="Em % da meta; o aviso sai uma vez por marco."
    )


class ConfiguracaoMetas(BaseModel):
    metas: list[Meta]
    marcos: list[int]


class ProgressoMeta(BaseModel):
    meta_id: int
    nivel: Nivel
    alvo: str
    periodo: Periodo
    rotulo_periodo: str = Field(examples=["novembro/2026"])
    inicio: date
    fim: date
    valor: Decimal
    realizado: Decimal
    percentual: Decimal = Field(description="Realizado / meta, em %.")
    especifica: bool = Field(description="Meta só deste período (não a que vale sempre).")


class ProgressoMetas(BaseModel):
    dia: date
    itens: list[ProgressoMeta]


class VendedorOpcao(BaseModel):
    id_erp: str
    nome: str
