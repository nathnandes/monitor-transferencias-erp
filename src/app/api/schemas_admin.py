from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas import DataUTC
from app.api.schemas_auth import AbaNome

_MAX_ENTRADA = 256

Papel = Literal["ADMIN", "OPERADOR"]
ModuloNome = Literal[
    "DASHBOARD",
    "TRANSFERENCIAS",
    "ESTOQUE",
    "VENDAS",
    "FINANCEIRO",
    "ALERTAS",
    "ADMINISTRACAO",
]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CriarUsuarioEntrada(_Entrada):
    username: str = Field(max_length=_MAX_ENTRADA, examples=["joao.silva"])
    nome_exibicao: str = Field(max_length=_MAX_ENTRADA, examples=["João Silva"])
    password_temporaria: str = Field(
        max_length=_MAX_ENTRADA,
        description="Senha inicial do usuário (mínimo de 4 caracteres).",
    )
    exigir_troca_senha: bool = Field(
        default=True,
        description="Obriga o usuário a trocar a senha no primeiro acesso.",
    )
    role: Papel
    modulos: list[ModuloNome] | None = Field(
        default=None,
        description=(
            "Módulos liberados. Omitido: padrão do papel (ADMIN → ADMINISTRACAO + "
            "DASHBOARD; OPERADOR → nenhum). ADMINISTRACAO só para ADMIN."
        ),
        examples=[["DASHBOARD", "TRANSFERENCIAS"]],
    )
    sessao_continua: bool = Field(
        default=False,
        description=("Modo TV: a sessão se renova sozinha e só termina no Sair. Só para OPERADOR."),
    )
    perfil_id: int | None = Field(
        default=None,
        description="Perfil de acesso: com ele, os módulos e as abas vêm do perfil.",
    )


class AtualizarUsuarioEntrada(_Entrada):
    nome_exibicao: str | None = Field(default=None, max_length=_MAX_ENTRADA)
    role: Papel | None = None
    ativo: bool | None = None
    modulos: list[ModuloNome] | None = Field(
        default=None, description="Conjunto completo de módulos (substitui o atual)."
    )
    sessao_continua: bool | None = Field(
        default=None, description="Modo TV (só OPERADOR). Desligar encerra a renovação."
    )
    perfil_id: int | None = Field(
        default=None,
        description="Perfil de acesso. Omitido: não muda; `null`: tira o perfil.",
    )


class RedefinirSenhaEntrada(_Entrada):
    password_temporaria: str = Field(max_length=_MAX_ENTRADA)
    exigir_troca_senha: bool = Field(
        default=True,
        description="Obriga o usuário a trocar a senha no próximo acesso.",
    )


class PermissoesEntrada(_Entrada):
    modulos: list[ModuloNome] = Field(
        description="Conjunto completo de módulos (substitui o atual).",
        examples=[["DASHBOARD", "TRANSFERENCIAS"]],
    )


class PerfilResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str


class UsuarioAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str = Field(examples=["joao.silva"])
    nome_exibicao: str = Field(examples=["João Silva"])
    role: Papel
    ativo: bool
    must_change_password: bool
    sessao_continua: bool = Field(description="Modo TV: sessão renovada até o Sair.")
    perfil: PerfilResumo | None = Field(
        description="Perfil de acesso; null: módulos da própria pessoa e todas as abas."
    )
    last_login_at: DataUTC | None
    created_at: DataUTC
    updated_at: DataUTC


class UsuarioAdminDetalhe(UsuarioAdmin):
    modulos: list[ModuloNome] = Field(
        description=(
            "Módulos da própria pessoa (valem enquanto o usuário estiver ativo e sem perfil)."
        )
    )


class PaginaUsuarios(BaseModel):
    total: int = Field(description="Total de usuários que atendem aos filtros.")
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    itens: list[UsuarioAdmin]


class PermissoesAdmin(BaseModel):
    user_id: int
    modulos: list[ModuloNome] = Field(examples=[["DASHBOARD", "TRANSFERENCIAS"]])


ModuloDePerfil = Literal[
    "DASHBOARD", "TRANSFERENCIAS", "ESTOQUE", "VENDAS", "FINANCEIRO", "ALERTAS"
]


class PerfilEntrada(_Entrada):
    nome: str = Field(max_length=_MAX_ENTRADA, examples=["Estoquista"])
    descricao: str | None = Field(default=None, max_length=_MAX_ENTRADA)
    modulos: list[ModuloDePerfil] = Field(
        description="Módulos (abas do menu). Administração acompanha o papel ADMIN.",
        examples=[["ESTOQUE"]],
    )
    abas: list[AbaNome] = Field(
        description="Sub-abas visíveis. Cada uma precisa do seu módulo.",
        examples=[["ESTOQUE.AVULSAS", "ESTOQUE.JUSTIFICATIVAS"]],
    )
    tela_inicial: str | None = Field(
        default=None,
        max_length=40,
        description="Módulo ou sub-aba que abre no login; null: o primeiro módulo.",
        examples=["ESTOQUE.AVULSAS"],
    )


class PerfilAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    descricao: str | None
    modulos: list[ModuloDePerfil]
    abas: list[AbaNome]
    tela_inicial: str | None
    usuarios: int = Field(description="Quantos usuários usam o perfil.")
    created_at: DataUTC
    updated_at: DataUTC
