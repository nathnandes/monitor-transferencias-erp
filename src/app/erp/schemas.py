from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.erp.errors import ErpApiRespostaInvalidaError

CONTENT_TYPE_TOKEN = "application/x-www-form-urlencoded"
GRANT_TYPE_TOKEN = "password"


class PedidoToken(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_id: str
    client_secret: SecretStr
    username: str
    password: SecretStr

    def to_form(self) -> dict[str, str]:
        return {
            "client_id": self.client_id,
            "grant_type": GRANT_TYPE_TOKEN,
            "client_secret": self.client_secret.get_secret_value(),
            "username": self.username,
            "password": self.password.get_secret_value(),
        }


def cabecalho_autorizacao(token: SecretStr) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.get_secret_value()}"}


class TokenResposta(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: SecretStr
    token_type: str = "bearer"

    expires_in: int | None = Field(default=None, gt=0)

    @field_validator("access_token")
    @classmethod
    def _nao_vazio(cls, valor: SecretStr) -> SecretStr:
        if not valor.get_secret_value().strip():
            raise ValueError("access_token vazio")
        return valor


class Operador(StrEnum):
    IGUAL = "IGUAL"
    IGUAL_NULL = "IGUAL_NULL"
    EQUAL = "EQUAL"
    MENOR = "MENOR"
    MAIOR = "MAIOR"
    LIKE = "LIKE"
    MENOR_IGUAL = "MENOR_IGUAL"
    MAIOR_IGUAL = "MAIOR_IGUAL"


class OperadorLogico(StrEnum):
    AND = "AND"


class Clausula(BaseModel):
    model_config = ConfigDict(frozen=True)

    campo: str = Field(min_length=1)
    operador: Operador
    valor: str = ""
    operador_logico: OperadorLogico = OperadorLogico.AND

    def to_payload(self) -> dict[str, str]:
        return {
            "campo": self.campo,
            "valor": self.valor,
            "operadorLogico": self.operador_logico.value,
            "operador": self.operador.value,
        }


class RequisicaoPaginada(BaseModel):
    model_config = ConfigDict(frozen=True)

    pagina: int = Field(default=1, ge=1)
    clausulas: tuple[Clausula, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "page": self.pagina,
            "clausulas": [c.to_payload() for c in self.clausulas],
        }

    def proxima(self) -> "RequisicaoPaginada":
        return self.model_copy(update={"pagina": self.pagina + 1})


class RespostaPaginada(BaseModel):
    model_config = ConfigDict(frozen=True)

    pagina: int
    registros: list[dict[str, Any]]
    total: int | None
    tem_proxima: bool


CAMPO_TOTAL_PADRAO = "Total"
CAMPO_TEM_PROXIMA_PADRAO = "hasNext"


def _como_bool(valor: Any, campo: str) -> bool:

    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str) and valor.strip().lower() in {"true", "false"}:
        return valor.strip().lower() == "true"
    raise ErpApiRespostaInvalidaError(f"campo '{campo}' nao e booleano")


def _nomes_das_chaves(payload: Mapping[Any, Any], limite: int = 20) -> list[str]:
    return sorted(str(k)[:50] for k in payload)[:limite]


def interpretar_pagina(
    payload: Any,
    *,
    pagina: int,
    campo_registros: str,
    campo_total: str = CAMPO_TOTAL_PADRAO,
    campo_tem_proxima: str = CAMPO_TEM_PROXIMA_PADRAO,
) -> RespostaPaginada:
    if not isinstance(payload, Mapping):
        raise ErpApiRespostaInvalidaError("resposta paginada nao e um objeto JSON")

    if campo_registros not in payload:
        raise ErpApiRespostaInvalidaError(
            f"campo de registros '{campo_registros}' ausente; chaves recebidas: "
            f"{_nomes_das_chaves(payload)}"
        )
    registros = payload[campo_registros]
    if not isinstance(registros, list) or not all(isinstance(r, Mapping) for r in registros):
        raise ErpApiRespostaInvalidaError(f"campo '{campo_registros}' nao e uma lista de objetos")

    if campo_tem_proxima not in payload:
        raise ErpApiRespostaInvalidaError(
            f"campo '{campo_tem_proxima}' ausente; chaves recebidas: {_nomes_das_chaves(payload)}"
        )
    tem_proxima = _como_bool(payload[campo_tem_proxima], campo_tem_proxima)

    total_bruto = payload.get(campo_total)
    total: int | None
    if total_bruto is None:
        total = None
    elif isinstance(total_bruto, bool):
        raise ErpApiRespostaInvalidaError(f"campo '{campo_total}' nao e inteiro")
    else:
        try:
            total = int(total_bruto)
        except (TypeError, ValueError):
            raise ErpApiRespostaInvalidaError(f"campo '{campo_total}' nao e inteiro") from None

    return RespostaPaginada(
        pagina=pagina,
        registros=[dict(r) for r in registros],
        total=total,
        tem_proxima=tem_proxima,
    )
