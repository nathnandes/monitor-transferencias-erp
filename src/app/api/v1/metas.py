from datetime import date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import schemas_metas as schemas
from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep, SessionLeituraDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS, Erro
from app.core.config import get_settings
from app.database.models import Vendedor
from app.dominio.modulos import Modulo
from app.services import atividades
from app.services import metas as service
from app.services.vendas import eh_vendedor_generico

router = APIRouter(
    prefix="/vendas/metas",
    tags=["vendas"],
    dependencies=[Depends(exigir_modulo(Modulo.VENDAS))],
    responses=RESPOSTAS_PROTEGIDAS,
)

Respostas = dict[int | str, dict[str, Any]]
_R422: Respostas = {422: {"model": Erro, "description": "Meta inválida."}}
_ROTULO_PERIODO = {"DIA": "diária", "SEMANA": "semanal", "MES": "mensal"}


def _configuracao(db: Session) -> schemas.ConfiguracaoMetas:
    return schemas.ConfiguracaoMetas(
        metas=[
            schemas.Meta(
                id=m.meta.id,
                nivel=m.meta.nivel,
                empresa_id=m.meta.empresa_id,
                id_vendedor=m.meta.id_vendedor,
                alvo=m.alvo,
                periodo=m.meta.periodo,
                referencia=m.meta.referencia,
                valor=m.meta.valor,
                atualizado_por=m.meta.usuario_nome,
                atualizado_em=m.meta.updated_at,
            )
            for m in service.listar(db)
        ],
        marcos=service.marcos(db),
    )


def _hoje() -> date:
    return datetime.now(ZoneInfo(get_settings().tz)).date()


@router.get("", summary="Metas cadastradas e marcos de aviso")
def listar(db: SessionLeituraDep) -> schemas.ConfiguracaoMetas:
    return _configuracao(db)


@router.get("/progresso", summary="Quanto já foi vendido de cada meta em vigor")
def progresso(
    db: SessionLeituraDep,
    dia: Annotated[
        date | None, Query(description="Dia de referência (padrão: hoje no fuso TZ).")
    ] = None,
) -> schemas.ProgressoMetas:
    dia = dia or _hoje()
    return schemas.ProgressoMetas(
        dia=dia,
        itens=[
            schemas.ProgressoMeta(
                meta_id=p.meta.id,
                nivel=p.meta.nivel,
                alvo=p.alvo,
                periodo=p.meta.periodo,
                rotulo_periodo=service.rotulo_periodo(p.meta.periodo, p.inicio),
                inicio=p.inicio,
                fim=p.fim,
                valor=p.meta.valor,
                realizado=p.realizado,
                percentual=p.percentual,
                especifica=p.meta.referencia is not None,
            )
            for p in service.progresso(db, dia)
        ],
    )


@router.get("/vendedores", summary="Vendedores para escolher na meta (sem os genéricos)")
def vendedores(db: SessionLeituraDep) -> list[schemas.VendedorOpcao]:
    return [
        schemas.VendedorOpcao(id_erp=v.id_erp, nome=v.nome or v.id_erp)
        for v in db.scalars(select(Vendedor).order_by(Vendedor.nome))
        if not eh_vendedor_generico(v.nome)
    ]


@router.put("", summary="Cria ou troca uma meta (ADMIN)", responses=_R422)
def salvar(
    dados: schemas.MetaEntrada, db: SessionDep, admin: AdminDep
) -> schemas.ConfiguracaoMetas:
    try:
        meta = service.salvar(db, usuario=admin, **dados.model_dump())
    except service.MetaInvalida as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from None
    [alvo] = [m.alvo for m in service.listar(db) if m.meta.id == meta.id]
    quando = (
        f" só em {service.rotulo_periodo(meta.periodo, meta.referencia)}" if meta.referencia else ""
    )
    atividades.registrar(
        db,
        "metas_alteradas",
        f"{admin.nome_exibicao} definiu a meta {_ROTULO_PERIODO[meta.periodo]} de {alvo}"
        f" em {service.moeda(meta.valor)}{quando}",
        usuario=admin,
        empresas=[meta.empresa_id] if meta.empresa_id else [],
    )
    db.commit()
    return _configuracao(db)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui uma meta (ADMIN)",
    responses={404: {"model": Erro, "description": "Meta não encontrada."}},
)
def excluir(
    id: Annotated[int, Path(description="Id da meta.")], db: SessionDep, admin: AdminDep
) -> Response:
    alvo = next((m.alvo for m in service.listar(db) if m.meta.id == id), "")
    try:
        meta = service.excluir(db, id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meta não encontrada.") from None
    atividades.registrar(
        db,
        "metas_alteradas",
        f"{admin.nome_exibicao} excluiu a meta {_ROTULO_PERIODO[meta.periodo]} de {alvo}",
        usuario=admin,
        empresas=[meta.empresa_id] if meta.empresa_id else [],
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/marcos", summary="Muda os marcos de aviso, em % da meta (ADMIN)", responses=_R422)
def definir_marcos(
    dados: schemas.Marcos, db: SessionDep, admin: AdminDep
) -> schemas.ConfiguracaoMetas:
    try:
        marcos = service.definir_marcos(db, dados.marcos, admin)
    except service.MetaInvalida as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from None
    atividades.registrar(
        db,
        "metas_alteradas",
        f"{admin.nome_exibicao} mudou os marcos de aviso das metas para "
        + ", ".join(f"{m}%" for m in marcos),
        usuario=admin,
    )
    db.commit()
    return _configuracao(db)
