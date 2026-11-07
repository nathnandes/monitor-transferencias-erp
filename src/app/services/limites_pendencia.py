from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models import LimitesPendencia
from app.dominio.transferencias import LIMITE_MAXIMO_HORAS, LIMITES_PADRAO, Limites


@dataclass(frozen=True)
class LimitesGravados:
    limites: Limites
    usuario_nome: str | None
    atualizado_em: datetime | None


def ler(db: Session) -> LimitesGravados:
    p = db.get(LimitesPendencia, 1)
    if p is None:
        return LimitesGravados(LIMITES_PADRAO, None, None)
    return LimitesGravados(Limites(p.horas_atencao, p.horas_critico), p.usuario_nome, p.updated_at)


def limites(db: Session) -> Limites:
    return ler(db).limites


def definir(
    db: Session,
    horas_atencao: int,
    horas_critico: int,
    *,
    usuario_id: int | None,
    usuario_nome: str,
    agora: datetime,
) -> LimitesGravados:
    if not 0 < horas_atencao < horas_critico <= LIMITE_MAXIMO_HORAS:
        raise ValueError(
            "A atenção deve vir antes do crítico, entre 1 e "
            f"{LIMITE_MAXIMO_HORAS} horas (atenção {horas_atencao} h, crítico {horas_critico} h)."
        )
    p = db.get(LimitesPendencia, 1)
    if p is None:
        p = LimitesPendencia(id=1)
        db.add(p)
    p.horas_atencao = horas_atencao
    p.horas_critico = horas_critico
    p.usuario_id = usuario_id
    p.usuario_nome = usuario_nome
    p.updated_at = agora
    db.flush()
    return LimitesGravados(Limites(horas_atencao, horas_critico), usuario_nome, agora)
