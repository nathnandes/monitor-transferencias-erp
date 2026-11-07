from datetime import datetime
from math import ceil
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionLeituraDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.dominio.modulos import Modulo
from app.rules.catalogo import CATALOGO
from app.services import atividades as service

router = APIRouter(
    prefix="/admin/atividades",
    tags=["admin"],
    dependencies=[Depends(exigir_modulo(Modulo.ADMINISTRACAO))],
    responses=RESPOSTAS_PROTEGIDAS,
)


class TipoAtividade(BaseModel):
    chave: str = Field(examples=["login"])
    nome: str = Field(examples=["Entrada no sistema"])


class AtividadeRegistrada(BaseModel):
    id: int
    tipo: str = Field(examples=["login"])
    tipo_nome: str = Field(examples=["Entrada no sistema"])
    usuario_nome: str = Field(description="Quem fez; no login recusado, o usuário digitado.")
    ip: str | None
    resumo: str = Field(examples=["MARIA entrou no sistema"])
    detalhe: str | None
    ocorrida_em: datetime


class PaginaAtividades(BaseModel):
    total: int
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    tipos: list[TipoAtividade] = Field(description="Os tipos de atividade, para o filtro.")
    itens: list[AtividadeRegistrada]


def _nome(tipo: str) -> str:
    definicao = CATALOGO.get(tipo)
    return definicao.nome if definicao else tipo


@router.get("", summary="Histórico de login, saída e alterações, do mais recente ao mais antigo")
def listar(
    db: SessionLeituraDep,
    admin: AdminDep,
    tipo: Annotated[str | None, Query(max_length=50, description="Só um tipo.")] = None,
    usuario: Annotated[
        str | None, Query(max_length=100, description="Parte do nome de quem fez.")
    ] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanho_pagina: Annotated[int, Query(ge=1, le=service.TAMANHO_PAGINA_MAXIMO)] = 50,
) -> PaginaAtividades:
    resultado = service.listar(
        db, tipo=tipo, usuario=usuario, pagina=pagina, tamanho=tamanho_pagina
    )
    return PaginaAtividades(
        total=resultado.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(resultado.total / tamanho_pagina),
        tipos=[
            TipoAtividade(chave=d.regra, nome=d.nome)
            for d in CATALOGO.values()
            if d.tipo != "alerta"
        ],
        itens=[
            AtividadeRegistrada(
                id=a.id,
                tipo=a.tipo,
                tipo_nome=_nome(a.tipo),
                usuario_nome=a.usuario_nome,
                ip=a.ip,
                resumo=a.resumo,
                detalhe=a.detalhe,
                ocorrida_em=a.ocorrida_em,
            )
            for a in resultado.itens
        ],
    )
