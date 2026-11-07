from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_MAX_ENTRADA = 256


class LoginEntrada(BaseModel):
    username: str = Field(max_length=_MAX_ENTRADA, examples=["maria"])
    password: str = Field(max_length=_MAX_ENTRADA)


class TrocaSenhaEntrada(BaseModel):
    current_password: str = Field(max_length=_MAX_ENTRADA)
    new_password: str = Field(max_length=_MAX_ENTRADA)


class UsuarioAutenticado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str = Field(examples=["maria"])
    nome_exibicao: str = Field(examples=["Maria Silva"])
    role: Literal["ADMIN", "OPERADOR"]
    ativo: bool
    must_change_password: bool
    sessao_continua: bool = Field(
        description="Modo TV: o frontend renova o token em /auth/renew até o Sair."
    )


class TokenAcesso(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Validade do token, em segundos.", examples=[1800])
    user: UsuarioAutenticado


AbaNome = Literal[
    "DASHBOARD.TV",
    "TRANSFERENCIAS.CONTROLE",
    "ESTOQUE.SALDOS",
    "ESTOQUE.LOJA",
    "ESTOQUE.LIVRO",
    "ESTOQUE.BALANCO",
    "ESTOQUE.AVULSAS",
    "ESTOQUE.JUSTIFICATIVAS",
    "VENDAS.TV",
    "VENDAS.GERAL",
    "VENDAS.EMPRESA_1",
    "VENDAS.EMPRESA_2",
    "VENDAS.EMPRESA_3",
    "VENDAS.EMPRESA_6",
]


class PermissoesUsuario(BaseModel):
    modulos: list[
        Literal[
            "DASHBOARD",
            "TRANSFERENCIAS",
            "ESTOQUE",
            "VENDAS",
            "FINANCEIRO",
            "ALERTAS",
            "ADMINISTRACAO",
        ]
    ] = Field(examples=[["DASHBOARD", "TRANSFERENCIAS"]])
    abas: list[AbaNome] | None = Field(
        default=None,
        description="Sub-abas do perfil de acesso; null: sem perfil, todas as dos módulos.",
    )
    tela_inicial: str | None = Field(
        default=None,
        description="Módulo ou sub-aba que abre no login (do perfil); null: o primeiro módulo.",
        examples=["ESTOQUE.AVULSAS"],
    )


class ErroSenhaFraca(BaseModel):
    mensagem: str = Field(examples=["Nova senha não atende à política."])
    problemas: list[str] = Field(examples=[["ao menos um numero"]])


class ErroPolitica(BaseModel):
    detail: ErroSenhaFraca
