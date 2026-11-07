from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, delete, exists, or_, select
from sqlalchemy.orm import Session

from app.database.models import Empresa, ExcecaoCobertura, Produto, Usuario


class ItemNaoEncontrado(LookupError):
    pass


@dataclass(frozen=True)
class Excecao:
    empresa: Empresa
    id_produto: str
    id_subproduto: str
    descricao: str | None
    motivo: str | None
    usuario_nome: str
    criado_em: datetime


def em_excecao(
    empresa_id: ColumnElement[int] | int,
    id_produto: ColumnElement[str],
    id_subproduto: ColumnElement[str],
) -> ColumnElement[bool]:
    x = ExcecaoCobertura
    return exists(
        select(x.empresa_id).where(
            x.empresa_id == empresa_id,
            x.id_produto == id_produto,
            x.id_subproduto == id_subproduto,
        )
    )


def chaves(db: Session) -> set[tuple[int, str, str]]:
    x = ExcecaoCobertura
    return {
        (e, p, s) for e, p, s in db.execute(select(x.empresa_id, x.id_produto, x.id_subproduto))
    }


def listar(db: Session, empresa_id: int | None = None) -> list[Excecao]:
    x = ExcecaoCobertura
    consulta = (
        select(x, Empresa, Produto.descricao_resumida, Produto.descricao)
        .join(Empresa, Empresa.id == x.empresa_id)
        .outerjoin(
            Produto,
            (Produto.id_produto == x.id_produto) & (Produto.id_subproduto == x.id_subproduto),
        )
        .order_by(Empresa.codigo, x.id_produto, x.id_subproduto)
    )
    if empresa_id is not None:
        consulta = consulta.where(x.empresa_id == empresa_id)
    return [
        Excecao(
            empresa,
            e.id_produto,
            e.id_subproduto,
            resumida or descricao,
            e.motivo,
            e.usuario_nome,
            e.criado_em,
        )
        for e, empresa, resumida, descricao in db.execute(consulta)
    ]


def incluir(
    db: Session,
    empresa: Empresa,
    codigo: str,
    *,
    motivo: str | None,
    usuario: Usuario,
    agora: datetime,
) -> list[tuple[str, str]]:
    codigo = codigo.strip()
    itens: Sequence[tuple[str, str]] = [
        (p, s)
        for p, s in db.execute(
            select(Produto.id_produto, Produto.id_subproduto)
            .where(or_(Produto.id_subproduto == codigo, Produto.id_produto == codigo))
            .order_by(Produto.id_subproduto)
        )
    ]
    if not itens:
        raise ItemNaoEncontrado(f"Produto {codigo} não encontrado no cadastro.")

    if any(s == codigo for _, s in itens):
        itens = [(p, s) for p, s in itens if s == codigo]
    ja = {k[1:] for k in chaves(db) if k[0] == empresa.id}
    novos = [i for i in itens if i not in ja]
    for p, s in novos:
        db.add(
            ExcecaoCobertura(
                empresa_id=empresa.id,
                id_produto=p,
                id_subproduto=s,
                motivo=(motivo or "").strip() or None,
                usuario_id=usuario.id,
                usuario_nome=usuario.nome_exibicao,
                criado_em=agora,
            )
        )
    db.flush()
    return novos


def remover(db: Session, empresa: Empresa, id_produto: str, id_subproduto: str) -> bool:
    x = ExcecaoCobertura
    resultado = db.execute(
        delete(x).where(
            x.empresa_id == empresa.id, x.id_produto == id_produto, x.id_subproduto == id_subproduto
        )
    )
    return bool(resultado.rowcount)  # type: ignore[attr-defined]
