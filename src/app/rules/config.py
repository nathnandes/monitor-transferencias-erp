from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models import AlertaConfiguracao, AlertaDestino
from app.rules.catalogo import CATALOGO
from app.rules.regras import NIVEL_SEVERIDADE


@dataclass
class ConfigRegra:
    regra: str
    ativo: bool
    campos: list[str]
    destinos: list[AlertaDestino] = field(default_factory=list)


def _padrao(regra: str, destinos_padrao: list[AlertaDestino]) -> ConfigRegra:
    definicao = CATALOGO.get(regra)
    return ConfigRegra(
        regra=regra,
        ativo=definicao.ativo_padrao if definicao else True,
        campos=definicao.campos_padrao if definicao else [],
        destinos=destinos_padrao,
    )


class Configuracao:
    def __init__(self, regras: dict[str, ConfigRegra], destinos_padrao: list[AlertaDestino]):
        self._regras = regras
        self._destinos_padrao = destinos_padrao

    def regra(self, nome: str) -> ConfigRegra:
        return self._regras.get(nome) or _padrao(nome, self._destinos_padrao)

    def destinos_para(
        self, regra: str, severidade: str | None, empresas_ids: Sequence[int]
    ) -> list[AlertaDestino]:
        return [
            d
            for d in self.regra(regra).destinos
            if d.ativo
            and (
                severidade is None
                or NIVEL_SEVERIDADE[severidade] >= NIVEL_SEVERIDADE[d.severidade_minima]
            )
            and (not d.empresas or not empresas_ids or set(d.empresas) & set(empresas_ids))
        ]


def carregar(db: Session) -> Configuracao:
    destinos_padrao = list(db.scalars(select(AlertaDestino).where(AlertaDestino.chat_id.is_(None))))
    linhas: Iterable[AlertaConfiguracao] = db.scalars(
        select(AlertaConfiguracao).options(selectinload(AlertaConfiguracao.destinos))
    )
    regras = {}
    for linha in linhas:
        regras[linha.regra] = ConfigRegra(
            regra=linha.regra,
            ativo=linha.ativo,
            campos=list(linha.campos),
            destinos=list(linha.destinos),
        )
    return Configuracao(regras, destinos_padrao)
