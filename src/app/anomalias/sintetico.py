from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal, get_args

import numpy as np

from app.anomalias.registros import RegistroTransferencia

TipoAnomalia = Literal[
    "valor_alto",
    "fora_de_horario",
    "rota_rara",
    "transito_longo",
    "divergencia",
    "combinada_sutil",
]
TIPOS_ANOMALIA: tuple[TipoAnomalia, ...] = get_args(TipoAnomalia)

ROTULOS_ANOMALIA: dict[TipoAnomalia, str] = {
    "valor_alto": "Valor muito alto",
    "fora_de_horario": "Fora de horário",
    "rota_rara": "Rota rara",
    "transito_longo": "Trânsito longo",
    "divergencia": "Divergência de quantidade",
    "combinada_sutil": "Combinada sutil",
}

EMPRESAS = tuple(f"Empresa {n:02d}" for n in range(1, 7))


_FUSO = timezone(timedelta(hours=-4))


_PESO_HORA = {
    7: 2,
    8: 6,
    9: 10,
    10: 12,
    11: 10,
    12: 4,
    13: 7,
    14: 11,
    15: 11,
    16: 9,
    17: 6,
    18: 3,
    19: 2,
    20: 1,
}

_PESO_DIA = (10.0, 10.0, 10.0, 10.0, 10.0, 4.0, 0.0)


@dataclass(frozen=True)
class ConjuntoSintetico:
    registros: list[RegistroTransferencia]

    rotulos: dict[str, TipoAnomalia]
    fim: datetime


@dataclass(frozen=True)
class _PerfilRota:
    origem: str
    destino: str
    peso: float
    valor_mediano: float
    transito_mediano_h: float
    itens_medio: float


def _perfis(rng: np.random.Generator) -> tuple[list[_PerfilRota], list[_PerfilRota]]:
    rotas = [(o, d) for o in EMPRESAS for d in EMPRESAS if o != d]
    ordem = rng.permutation(len(rotas))
    comuns, raras = ordem[:18], ordem[18:]

    def perfil(indice: int, peso: float) -> _PerfilRota:
        origem, destino = rotas[int(indice)]
        return _PerfilRota(
            origem=origem,
            destino=destino,
            peso=peso,
            valor_mediano=float(rng.lognormal(np.log(4_000), 0.7)),
            transito_mediano_h=float(rng.uniform(3, 30)),
            itens_medio=float(rng.uniform(4, 18)),
        )

    pesos = rng.dirichlet(np.full(len(comuns), 4.0))
    return (
        [perfil(i, float(p)) for i, p in zip(comuns, pesos, strict=True)],
        [perfil(i, 0.0) for i in raras],
    )


def _sortear_emissao(rng: np.random.Generator, inicio: datetime, dias: int) -> datetime:
    pesos_dia = np.array([_PESO_DIA[(inicio + timedelta(days=d)).weekday()] for d in range(dias)])
    dia = int(rng.choice(dias, p=pesos_dia / pesos_dia.sum()))
    horas = np.array(list(_PESO_HORA))
    pesos_hora = np.array(list(_PESO_HORA.values()), dtype=float)
    hora = int(rng.choice(horas, p=pesos_hora / pesos_hora.sum()))
    return inicio + timedelta(days=dia, hours=hora, minutes=int(rng.integers(60)))


def _normal(
    rng: np.random.Generator, numero: int, perfil: _PerfilRota, inicio: datetime, dias: int
) -> RegistroTransferencia:
    emitida = _sortear_emissao(rng, inicio, dias)
    itens = max(1, int(rng.poisson(perfil.itens_medio)))

    escala = itens / perfil.itens_medio
    valor = perfil.valor_mediano * escala * float(rng.lognormal(0, 0.35))
    enviada = float(itens * rng.uniform(2, 12))

    recebida = enviada - float(rng.uniform(0, 0.015) * enviada) if rng.random() < 0.03 else enviada
    transito = perfil.transito_mediano_h * float(rng.lognormal(0, 0.3))
    return RegistroTransferencia(
        id=f"SIM-{numero:06d}",
        origem=perfil.origem,
        destino=perfil.destino,
        valor=round(valor, 2),
        emitida_em=emitida,
        recebida_em=emitida + timedelta(hours=transito),
        quantidade_itens=itens,
        quantidade_enviada=round(enviada, 2),
        quantidade_recebida=round(recebida, 2),
    )


def _noite(rng: np.random.Generator, emitida: datetime) -> datetime:
    hora = int(rng.choice([22, 23, 0, 1, 2, 3, 4]))
    return emitida.replace(hour=hora, minute=int(rng.integers(60)))


def _deslocar(r: RegistroTransferencia, emitida: datetime) -> RegistroTransferencia:
    assert r.recebida_em is not None
    return replace(r, emitida_em=emitida, recebida_em=emitida + (r.recebida_em - r.emitida_em))


def _esticar_transito(r: RegistroTransferencia, fator: float) -> RegistroTransferencia:
    assert r.recebida_em is not None
    return replace(r, recebida_em=r.emitida_em + (r.recebida_em - r.emitida_em) * fator)


def _injetar(
    rng: np.random.Generator,
    r: RegistroTransferencia,
    tipo: TipoAnomalia,
    raras: list[_PerfilRota],
) -> RegistroTransferencia:
    if tipo == "valor_alto":
        return replace(r, valor=round(r.valor * float(rng.uniform(6, 15)), 2))
    if tipo == "fora_de_horario":
        emitida = r.emitida_em
        if rng.random() < 0.3:
            emitida += timedelta(days=6 - emitida.weekday())
        return _deslocar(r, _noite(rng, emitida))
    if tipo == "rota_rara":
        rota = raras[int(rng.integers(len(raras)))]
        return replace(r, origem=rota.origem, destino=rota.destino)
    if tipo == "transito_longo":
        return _esticar_transito(r, float(rng.uniform(5, 10)))
    if tipo == "divergencia":
        recebida = r.quantidade_enviada * (1 - float(rng.uniform(0.05, 0.25)))
        return replace(r, quantidade_recebida=round(recebida, 2))

    alterada = _esticar_transito(r, float(rng.uniform(2.0, 2.8)))
    alterada = replace(alterada, valor=round(r.valor * float(rng.uniform(2.2, 3.2)), 2))
    fim_do_dia = r.emitida_em.replace(hour=int(rng.choice([19, 20])))
    return _deslocar(alterada, fim_do_dia)


def _marcar_pendentes(
    registros: list[RegistroTransferencia], fim: datetime
) -> list[RegistroTransferencia]:
    return [
        replace(r, recebida_em=None, quantidade_recebida=None)
        if r.recebida_em is not None and r.recebida_em > fim
        else r
        for r in registros
    ]


def gerar(
    semente: int = 42,
    *,
    dias: int = 180,
    quantidade: int = 5_000,
    taxa_anomalias: float = 0.015,
    fim: datetime | None = None,
) -> ConjuntoSintetico:
    if not 0 <= taxa_anomalias < 1:
        raise ValueError("taxa_anomalias precisa estar entre 0 e 1")
    if dias < 7:
        raise ValueError("dias precisa ser pelo menos 7")
    rng = np.random.default_rng(semente)

    fim = fim or datetime(2026, 6, 30, 23, 59, tzinfo=_FUSO)
    inicio = fim.replace(hour=0, minute=0) - timedelta(days=dias - 1)

    comuns, raras = _perfis(rng)
    pesos = np.array([p.peso for p in comuns])
    registros = [
        _normal(rng, n, comuns[int(rng.choice(len(comuns), p=pesos))], inicio, dias)
        for n in range(1, quantidade + 1)
    ]

    total = round(quantidade * taxa_anomalias)
    escolhidos = rng.choice(quantidade, size=total, replace=False)
    rotulos: dict[str, TipoAnomalia] = {}
    for posicao, indice in enumerate(escolhidos):
        tipo = TIPOS_ANOMALIA[posicao % len(TIPOS_ANOMALIA)]
        original = registros[int(indice)]
        registros[int(indice)] = _injetar(rng, original, tipo, raras)
        rotulos[original.id] = tipo

    registros = _marcar_pendentes(registros, fim)
    registros.sort(key=lambda r: (r.emitida_em, r.id))
    return ConjuntoSintetico(registros=registros, rotulos=rotulos, fim=fim)
