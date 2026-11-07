from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS, Erro
from app.api.schemas_admin import PerfilAdmin, PerfilEntrada
from app.core.logging_config import get_logger
from app.database.models import PerfilAcesso
from app.dominio.modulos import Modulo
from app.services import atividades
from app.services import perfis as service
from app.services.autorizacao import ordenar

logger = get_logger(__name__)

router = APIRouter(
    prefix="/admin/perfis",
    tags=["admin"],
    dependencies=[Depends(exigir_modulo(Modulo.ADMINISTRACAO))],
    responses=RESPOSTAS_PROTEGIDAS,
)

Respostas = dict[int | str, dict[str, Any]]
_R404: Respostas = {404: {"model": Erro, "description": "Perfil não encontrado."}}
_R409: Respostas = {409: {"model": Erro, "description": "Nome repetido ou perfil em uso."}}
_R422: Respostas = {422: {"model": Erro, "description": "Aba sem o módulo, tela inicial fora."}}

IdPerfil = Annotated[int, Path(description="Id do perfil.")]


def _alvo(db: Session, perfil_id: int) -> PerfilAcesso:
    perfil = db.get(PerfilAcesso, perfil_id)
    if perfil is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil não encontrado.")
    return perfil


def _saida(perfil: PerfilAcesso, usuarios: int) -> PerfilAdmin:
    return PerfilAdmin.model_validate(
        {
            "id": perfil.id,
            "nome": perfil.nome,
            "descricao": perfil.descricao,
            "modulos": ordenar(service.modulos_do_perfil(perfil)),
            "abas": service.abas_do_perfil(perfil),
            "tela_inicial": perfil.tela_inicial,
            "usuarios": usuarios,
            "created_at": perfil.created_at,
            "updated_at": perfil.updated_at,
        }
    )


def _dados(dados: PerfilEntrada) -> service.DadosPerfil:
    try:
        return service.validar(
            dados.nome, dados.descricao, dados.modulos, dados.abas, dados.tela_inicial
        )
    except service.PerfilInvalidoError as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from None


@router.get("", summary="Lista os perfis de acesso, com quantos usuários usam cada um")
def listar(db: SessionDep, admin: AdminDep) -> list[PerfilAdmin]:
    return [_saida(p, n) for p, n in service.listar(db)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Cria um perfil de acesso",
    responses={**_R409, **_R422},
)
def criar(dados: PerfilEntrada, db: SessionDep, admin: AdminDep) -> PerfilAdmin:
    validados = _dados(dados)
    try:
        perfil = service.criar(db, validados)
    except service.PerfilEmUsoError as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from None
    atividades.registrar(
        db, "perfis_alterados", f"{admin.nome_exibicao} criou o perfil {perfil.nome}", usuario=admin
    )
    db.commit()
    db.refresh(perfil)
    logger.info("admin.perfil.criado ator_id=%s perfil_id=%s", admin.id, perfil.id)
    return _saida(perfil, 0)


@router.put(
    "/{id}",
    summary="Substitui um perfil de acesso",
    description="Vale na hora para a API; o menu de quem usa o perfil muda no próximo login.",
    responses={**_R404, **_R409, **_R422},
)
def atualizar(id: IdPerfil, dados: PerfilEntrada, db: SessionDep, admin: AdminDep) -> PerfilAdmin:
    perfil = _alvo(db, id)
    validados = _dados(dados)
    try:
        service.atualizar(db, perfil, validados)
    except service.PerfilEmUsoError as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from None
    atividades.registrar(
        db,
        "perfis_alterados",
        f"{admin.nome_exibicao} alterou o perfil {perfil.nome}",
        usuario=admin,
    )
    db.commit()
    db.refresh(perfil)
    logger.info("admin.perfil.atualizado ator_id=%s perfil_id=%s", admin.id, perfil.id)
    return _saida(perfil, service.usuarios_do_perfil(db, perfil))


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um perfil sem usuários",
    responses={**_R404, **_R409},
)
def excluir(id: IdPerfil, db: SessionDep, admin: AdminDep) -> Response:
    perfil = _alvo(db, id)
    nome = perfil.nome
    try:
        service.excluir(db, perfil)
    except service.PerfilEmUsoError as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from None
    atividades.registrar(
        db, "perfis_alterados", f"{admin.nome_exibicao} excluiu o perfil {nome}", usuario=admin
    )
    db.commit()
    logger.info("admin.perfil.excluido ator_id=%s perfil_id=%s", admin.id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
