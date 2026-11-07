from fastapi import APIRouter

from app.api.v1 import (
    admin_alertas,
    admin_atividades,
    admin_estoque_baixo,
    admin_perfis,
    admin_usuarios,
    alertas,
    auth,
    dashboard,
    empresas,
    estoque,
    financeiro,
    frescor,
    metas,
    sincronizacao,
    transferencias,
    transferencias_controle,
    vendas,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(admin_usuarios.router)
router.include_router(admin_perfis.router)
router.include_router(admin_alertas.router)
router.include_router(admin_atividades.router)
router.include_router(admin_estoque_baixo.router)
router.include_router(empresas.router)
router.include_router(transferencias_controle.router)
router.include_router(transferencias.router)
router.include_router(dashboard.router)
router.include_router(alertas.router)
router.include_router(estoque.router)
router.include_router(metas.router)
router.include_router(vendas.router)
router.include_router(financeiro.router)
router.include_router(sincronizacao.router)
router.include_router(frescor.router)
