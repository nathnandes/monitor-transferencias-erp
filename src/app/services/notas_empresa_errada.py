from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.orm import Session, aliased

from app.database.models import Empresa, MovimentoEstoque, NotaMovimento
from app.dominio.empresa_errada import CATEGORIA_PERMITIDA


def condicao_destino_do_grupo(n: type[NotaMovimento] = NotaMovimento) -> ColumnElement[bool]:
    outra = aliased(Empresa)
    return and_(
        n.saida.is_(True),
        n.cancelada.is_not(True),
        exists().where(outra.cnpj == n.cnpj_destinatario, outra.id != n.empresa_id),
    )


def condicao_empresa_errada(
    tipo: ColumnElement[str], n: type[NotaMovimento] = NotaMovimento
) -> ColumnElement[bool]:
    return and_(condicao_destino_do_grupo(n), tipo != CATEGORIA_PERMITIDA)


@dataclass(frozen=True)
class NotaEmpresaErrada:
    empresa: Empresa
    destino: Empresa
    id_planilha: str
    numero: str | None
    dia: date
    momento: datetime | None
    usuario: str | None
    coi: int
    operacao: str | None
    itens: int
    valor: Decimal | None


def listar(db: Session, *, desde: date | None = None) -> list[NotaEmpresaErrada]:
    m = MovimentoEstoque
    n = NotaMovimento
    condicoes = [m.dia >= desde] if desde else []
    documentos = (
        select(
            m.empresa_id,
            m.id_planilha,
            func.max(m.dia).label("dia"),
            func.min(m.coi).label("coi"),
            func.max(m.operacao).label("operacao"),
            func.max(m.tipo).label("tipo"),
            func.count().label("itens"),
            func.sum(m.valor).label("valor"),
        )
        .where(*condicoes)
        .group_by(m.empresa_id, m.id_planilha)
        .subquery()
    )
    destino = aliased(Empresa)
    linhas = db.execute(
        select(documentos, n.numero, n.momento, n.usuario, destino.id.label("destino_id"))
        .join(
            n,
            (n.empresa_id == documentos.c.empresa_id) & (n.id_planilha == documentos.c.id_planilha),
        )
        .join(destino, (destino.cnpj == n.cnpj_destinatario) & (destino.id != n.empresa_id))
        .where(condicao_empresa_errada(documentos.c.tipo, n))
        .order_by(documentos.c.dia.desc(), n.momento.desc().nulls_last(), documentos.c.empresa_id)
    ).all()
    ids = {x.empresa_id for x in linhas} | {x.destino_id for x in linhas}
    empresas = {e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_(ids)))}
    return [
        NotaEmpresaErrada(
            empresa=empresas[x.empresa_id],
            destino=empresas[x.destino_id],
            id_planilha=x.id_planilha,
            numero=x.numero,
            dia=x.dia,
            momento=x.momento,
            usuario=(x.usuario or "").strip() or None,
            coi=x.coi,
            operacao=(x.operacao or "").strip() or None,
            itens=x.itens,
            valor=x.valor,
        )
        for x in linhas
    ]
