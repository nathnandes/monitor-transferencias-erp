from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, contains_eager, joinedload, selectinload

from app.database.models import Empresa, Transferencia
from app.services import controle_transferencias as controle
from app.services.comum import condicao_entre_empresas
from app.services.pipeline import SituacaoCoi, condicao_situacao_coi


class IntervaloDeDatasInvalido(ValueError):
    pass


@dataclass(frozen=True)
class FiltrosTransferencia:
    empresa_origem: str | None = None
    empresa_destino: str | None = None

    empresa: str | None = None
    status: str | None = None
    situacao_coi: SituacaoCoi | None = None

    emitida_por: str | None = None

    ocorrencia: controle.Ocorrencia | None = None
    data_inicial: date | None = None
    data_final: date | None = None

    def __post_init__(self) -> None:
        if self.data_inicial and self.data_final and self.data_inicial > self.data_final:
            raise IntervaloDeDatasInvalido(
                f"data_inicial ({self.data_inicial}) é posterior a data_final ({self.data_final})."
            )


@dataclass(frozen=True)
class Pagina:
    total: int
    itens: Sequence[Transferencia]


def _inicio_do_dia(dia: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(dia, time.min, tzinfo=tz)


def listar_transferencias(
    db: Session,
    filtros: FiltrosTransferencia,
    *,
    pagina: int,
    tamanho_pagina: int,
    tz: ZoneInfo,
    agora: datetime | None = None,
) -> Pagina:
    origem = aliased(Empresa, name="origem")
    destino = aliased(Empresa, name="destino")

    condicoes = [condicao_entre_empresas()]
    if filtros.empresa_origem:
        condicoes.append(origem.codigo == filtros.empresa_origem)
    if filtros.empresa_destino:
        condicoes.append(destino.codigo == filtros.empresa_destino)
    if filtros.empresa:
        condicoes.append(or_(origem.codigo == filtros.empresa, destino.codigo == filtros.empresa))
    if filtros.status:
        condicoes.append(Transferencia.status == filtros.status.upper())
    if filtros.situacao_coi:
        condicoes.append(condicao_situacao_coi(filtros.situacao_coi))
    if filtros.emitida_por:
        condicoes.append(
            func.upper(func.trim(Transferencia.usuario_emissao))
            == filtros.emitida_por.strip().upper()
        )
    if filtros.ocorrencia:
        ids = controle.ids_com_ocorrencia(
            db,
            controle.Filtros(
                empresa=filtros.empresa,
                data_inicial=filtros.data_inicial,
                data_final=filtros.data_final,
            ),
            filtros.ocorrencia,
            tz=tz,
            agora=agora or datetime.now(UTC),
        )
        condicoes.append(Transferencia.id.in_(ids))
    if filtros.data_inicial:
        condicoes.append(Transferencia.data_criacao >= _inicio_do_dia(filtros.data_inicial, tz))
    if filtros.data_final:
        dia_seguinte = _inicio_do_dia(filtros.data_final + timedelta(days=1), tz)
        condicoes.append(Transferencia.data_criacao < dia_seguinte)

    base = (
        select(Transferencia)
        .join(origem, Transferencia.empresa_origem_id == origem.id)
        .outerjoin(destino, Transferencia.empresa_destino_id == destino.id)
        .where(*condicoes)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    itens = db.scalars(
        base.options(
            contains_eager(Transferencia.empresa_origem.of_type(origem)),
            contains_eager(Transferencia.empresa_destino.of_type(destino)),
        )
        .order_by(Transferencia.data_criacao.desc().nulls_last(), Transferencia.id.desc())
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
    ).all()
    return Pagina(total=total, itens=itens)


def obter_transferencia(db: Session, id_: int) -> Transferencia | None:
    return db.scalar(
        select(Transferencia)
        .where(Transferencia.id == id_)
        .options(
            joinedload(Transferencia.empresa_origem),
            joinedload(Transferencia.empresa_destino),
            selectinload(Transferencia.itens),
        )
    )
