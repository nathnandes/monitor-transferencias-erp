from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep, SessionLeituraDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS, Erro
from app.core.config import get_settings
from app.dominio.modulos import Modulo
from app.services import atividades
from app.services import estoque_baixo as service

router = APIRouter(
    prefix="/admin/estoque-baixo",
    tags=["admin"],
    dependencies=[Depends(exigir_modulo(Modulo.ADMINISTRACAO))],
    responses=RESPOSTAS_PROTEGIDAS,
)


class ParametrosEstoqueBaixo(BaseModel):
    configurado: bool = Field(description="False: ninguém configurou ainda (não avisa).")
    ativo: bool
    dias_cobertura: int = Field(description="Dias de venda que se quer ter em estoque.")
    dias_por_empresa: dict[int, int] = Field(description="Dias por loja (id → dias), se diferente.")
    janela_dias: int = Field(description="Dias de vendas usados para medir o giro.")
    horarios: list[str] = Field(examples=[["08:00", "14:00"]])
    ultima_execucao: datetime | None
    atualizado_por: str | None
    atualizado_em: datetime | None


class ParametrosEstoqueBaixoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ativo: bool = True
    dias_cobertura: int = Field(ge=1, le=365, examples=[7])
    dias_por_empresa: dict[int, int] = Field(default_factory=dict)
    janela_dias: int = Field(default=30, ge=7, le=180)
    horarios: list[str] = Field(min_length=1, max_length=6, examples=[["08:00", "14:00"]])


class ProdutoBaixo(BaseModel):
    id_produto: str
    id_subproduto: str
    descricao: str | None
    disponivel: Decimal
    venda_media_diaria: Decimal
    minimo: Decimal


class SituacaoLoja(BaseModel):
    empresa_id: int
    codigo: str
    nome: str
    dias: int
    total: int
    produtos: list[ProdutoBaixo] = Field(description="Os mais urgentes primeiro (até `limite`).")


class SituacaoEstoqueBaixo(BaseModel):
    lojas: list[SituacaoLoja]


_PADRAO = ParametrosEstoqueBaixo(
    configurado=False,
    ativo=False,
    dias_cobertura=service.DIAS_PADRAO,
    dias_por_empresa={},
    janela_dias=service.JANELA_PADRAO,
    horarios=["08:00"],
    ultima_execucao=None,
    atualizado_por=None,
    atualizado_em=None,
)


def _parametros(db: Session) -> ParametrosEstoqueBaixo:
    p = service.parametros(db)
    if p is None:
        return _PADRAO
    return ParametrosEstoqueBaixo(
        configurado=True,
        ativo=p.ativo,
        dias_cobertura=p.dias_cobertura,
        dias_por_empresa={int(k): v for k, v in p.dias_por_empresa.items()},
        janela_dias=p.janela_dias,
        horarios=list(p.horarios),
        ultima_execucao=p.ultima_execucao,
        atualizado_por=p.usuario_nome,
        atualizado_em=p.updated_at,
    )


@router.get("", summary="Configuração do aviso de estoque baixo")
def ler(db: SessionLeituraDep, admin: AdminDep) -> ParametrosEstoqueBaixo:
    return _parametros(db)


@router.put(
    "",
    summary="Liga, desliga e configura o aviso de estoque baixo",
    responses={422: {"model": Erro, "description": "Configuração inválida."}},
)
def salvar(
    dados: ParametrosEstoqueBaixoEntrada, db: SessionDep, admin: AdminDep
) -> ParametrosEstoqueBaixo:
    try:
        p = service.salvar_parametros(db, usuario=admin, **dados.model_dump())
    except service.ParametrosInvalidos as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from None
    estado = "ligou" if p.ativo else "desligou"
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} {estado} o aviso de estoque baixo"
        f" ({p.dias_cobertura} dias de venda, às {', '.join(p.horarios)})",
        usuario=admin,
    )
    db.commit()
    return _parametros(db)


@router.get(
    "/situacao",
    summary="Produtos abaixo do mínimo agora, por loja (parâmetros salvos ou os padrões)",
)
def situacao(
    db: SessionLeituraDep,
    admin: AdminDep,
    limite: Annotated[int, Query(ge=1, le=500, description="Produtos por loja.")] = 20,
) -> SituacaoEstoqueBaixo:
    hoje: date = datetime.now(ZoneInfo(get_settings().tz)).date()
    return SituacaoEstoqueBaixo(
        lojas=[
            SituacaoLoja(
                empresa_id=s.empresa.id,
                codigo=s.empresa.codigo,
                nome=s.empresa.nome,
                dias=s.dias,
                total=len(s.baixos),
                produtos=[
                    ProdutoBaixo(
                        id_produto=b.id_produto,
                        id_subproduto=b.id_subproduto,
                        descricao=b.descricao,
                        disponivel=b.disponivel,
                        venda_media_diaria=b.media.quantize(Decimal("0.001")),
                        minimo=b.minimo.quantize(Decimal("0.01")),
                    )
                    for b in s.baixos[:limite]
                ],
            )
            for s in service.situacao(db, hoje)
        ]
    )
