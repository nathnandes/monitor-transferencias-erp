from fastapi import APIRouter, Depends, status

from app.api import schemas_sincronizacao as schemas
from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep, SessionLeituraDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.core.logging_config import get_logger
from app.dominio.modulos import Modulo
from app.services import atividades
from app.services import sincronizacao as service

logger = get_logger(__name__)

router = APIRouter(
    prefix="/sync",
    tags=["sincronizacao"],
    dependencies=[Depends(exigir_modulo(Modulo.ADMINISTRACAO))],
    responses=RESPOSTAS_PROTEGIDAS,
)


def _solicitar(db: SessionDep, admin: AdminDep, tipo: str) -> schemas.Solicitacao:
    pedido = service.solicitar(db, tipo, admin.username)
    resposta = schemas.Solicitacao.model_validate(pedido)
    atividades.registrar(
        db,
        "sincronizacao_pedida",
        f"{admin.nome_exibicao} pediu a sincronização de {tipo.replace('_', ' ')}",
        usuario=admin,
    )
    db.commit()
    logger.info("sync.solicitada tipo=%s pedido=%s ator_id=%s", tipo, pedido.id, admin.id)
    return resposta


@router.post(
    "/companies",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a sincronização de empresas (CAD_LOJAS)",
)
def sincronizar_empresas(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "empresas")


@router.post(
    "/stock",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a leitura incremental do estoque (o que mudou + reservas)",
)
def sincronizar_estoque(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "estoque")


@router.post(
    "/stock/full",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a leitura completa do estoque (demorada; desativa linhas que sumiram)",
)
def sincronizar_estoque_completo(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "estoque_completo")


@router.post(
    "/transfers",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a sincronização das transferências (notas com COI de transferência)",
)
def sincronizar_transferencias(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "transferencias")


@router.post(
    "/prices",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a leitura incremental de produtos e preços/custos (o que mudou)",
)
def sincronizar_precos(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "precos")


@router.post(
    "/prices/full",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a leitura completa de produtos e preços/custos (demorada)",
)
def sincronizar_precos_completo(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "precos_completo")


@router.post(
    "/sales",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a sincronização das vendas (janela recente + parte do histórico)",
)
def sincronizar_vendas(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "vendas")


@router.post(
    "/stock-movements",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede a sincronização das entradas/saídas avulsas e dos balanços de estoque",
)
def sincronizar_movimentos_estoque(db: SessionDep, admin: AdminDep) -> schemas.Solicitacao:
    return _solicitar(db, admin, "movimentos_estoque")


@router.get("/status", summary="Pedidos, últimas execuções e erros recentes")
def status_sincronizacao(db: SessionLeituraDep, _admin: AdminDep) -> schemas.StatusSincronizacao:
    s = service.status(db)
    return schemas.StatusSincronizacao(
        pendentes=[schemas.Solicitacao.model_validate(p) for p in s.pendentes],
        em_execucao=[schemas.Solicitacao.model_validate(p) for p in s.em_execucao],
        empresas=schemas.Execucao.model_validate(s.ultima_empresas) if s.ultima_empresas else None,
        estoque=schemas.Execucao.model_validate(s.ultima_estoque) if s.ultima_estoque else None,
        estoque_completo=(
            schemas.Execucao.model_validate(s.ultima_estoque_completo)
            if s.ultima_estoque_completo
            else None
        ),
        precos=schemas.Execucao.model_validate(s.ultima_precos) if s.ultima_precos else None,
        precos_completo=(
            schemas.Execucao.model_validate(s.ultima_precos_completo)
            if s.ultima_precos_completo
            else None
        ),
        estoque_por_empresa=[
            schemas.ExecucaoEmpresa.model_validate(e) for e in s.estoque_por_empresa
        ],
        erros_recentes=[schemas.ErroIntegracao.model_validate(e) for e in s.erros_recentes],
        resumo_estoque=schemas.ResumoSincronizacaoEstoque(**vars(s.estoque)),
    )
