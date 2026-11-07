from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severidade = Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
Canal = Literal["telegram", "whatsapp"]


class CampoAlerta(BaseModel):
    chave: str = Field(examples=["nota"])
    rotulo: str = Field(examples=["Nota"])
    padrao: bool = Field(description="Marcado quando a regra está no padrão.")


class RegraAlertaConfig(BaseModel):
    regra: str = Field(examples=["transferencia_atrasada"])
    tipo: Literal["alerta", "atividade", "meta", "estoque"] = Field(
        description=(
            "alerta: situação que abre e resolve; atividade: login, saída, alteração; "
            "meta: meta de vendas que chegou a um marco; estoque: resumo de estoque baixo."
        )
    )
    nome: str
    descricao: str
    ativo: bool
    personalizada: bool = Field(description="False = ainda no padrão (nada salvo).")
    campos_disponiveis: list[CampoAlerta]
    campos: list[str] = Field(description="Campos marcados, na ordem da mensagem.")
    destinos: list[int] = Field(description="Ids dos destinos que recebem esta regra.")


class DestinoAlerta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    canal: Canal = Field(description="Por onde a mensagem sai.")
    chat_id: str | None = Field(
        description=(
            "Telegram: o chat (nulo = o chat do .env, TELEGRAM_CHAT_ID). "
            "WhatsApp: o número com DDI e DDD, só dígitos."
        )
    )
    ativo: bool
    severidade_minima: Severidade
    empresas: list[int] = Field(description="Ids das empresas; vazio = todas.")


class VariavelModelo(BaseModel):
    chave: str = Field(examples=["nota"])
    rotulo: str = Field(examples=["Nota"])
    exemplo: str = Field(description="Valor usado na prévia.")


class ModeloMensagemAlerta(BaseModel):
    chave: str = Field(examples=["transferencia_coi_errado:aviso"])
    nome: str
    grupo: str = Field(description="Agrupamento na tela (a regra, ou o resumo do dia).")
    descricao: str
    variaveis: list[VariavelModelo]
    padrao: str = Field(description="Texto padrão (a mensagem de antes da personalização).")
    texto: str = Field(description="Texto em vigor: o personalizado ou o padrão.")
    personalizado: bool
    atualizado_por: str | None
    atualizado_em: datetime | None


class ConfiguracaoAlertas(BaseModel):
    regras: list[RegraAlertaConfig]
    destinos: list[DestinoAlerta]
    modelos: list[ModeloMensagemAlerta]


class ModeloMensagemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(max_length=3000, examples=["🚨 {titulo} · {nota}"])


class PreviaModelo(BaseModel):
    texto: str = Field(description="A mensagem com valores de exemplo.")


class RegraAlertaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ativo: bool
    campos: list[str] = Field(max_length=50)
    destinos: list[int] = Field(default_factory=list, max_length=50)


class DestinoAlertaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=100, examples=["Grupo Depósito 02"])
    canal: Canal = "telegram"
    chat_id: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Telegram: número do chat (ex.: -1001234567890) ou @canal; vazio = chat do .env. "
            "WhatsApp: obrigatório, com DDI e DDD (ex.: +55 11 98765-4321)."
        ),
    )
    ativo: bool = True
    severidade_minima: Severidade = "WARNING"
    empresas: list[int] = Field(default_factory=list, max_length=100)


StatusEnvio = Literal["PENDENTE", "ENVIADA", "FALHA", "DESCARTADA"]


class MensagemAvulsaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(min_length=1, max_length=4000, description="O texto, como vai ser enviado.")
    destinos: list[int] = Field(
        min_length=1, max_length=100, description="Ids dos destinos (WhatsApp ou Telegram)."
    )
    agendada_para: datetime | None = Field(
        default=None,
        description=(
            "Quando enviar. Vazio = agora (até 1 minuto). Sem fuso = hora local da empresa. "
            "Ignorado quando `horario` está preenchido."
        ),
        examples=["2026-11-06T08:00:00"],
    )
    horario: time | None = Field(
        default=None,
        description="Repetir todo dia nesta hora (fuso da empresa). Vazio = envio único.",
        examples=["18:00"],
    )
    dias_semana: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5, 6, 7],
        max_length=7,
        description="Dias da repetição: 1 = segunda ... 7 = domingo.",
    )


class PreviaMensagemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(min_length=1, max_length=4000)


class EnvioMensagemAvulsa(BaseModel):
    destino_id: int | None
    destino_nome: str
    canal: Canal
    status: StatusEnvio
    enviada_em: datetime | None
    ultimo_erro: str | None


class MensagemAvulsaSaida(BaseModel):
    id: int
    texto: str
    agendada_para: datetime = Field(
        description="Envio único: a hora marcada. Repetida: o próximo envio."
    )
    horario: time | None = Field(description="Preenchido = repete todo dia (nos dias_semana).")
    dias_semana: list[int]
    criada_por: str
    criada_em: datetime
    cancelada_em: datetime | None
    envios: list[EnvioMensagemAvulsa]


class ModeloMensagemAvulsaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=80, examples=["Resumo das 18h"])
    texto: str = Field(min_length=1, max_length=4000)


class ModeloMensagemAvulsaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    texto: str
    atualizado_por: str
    updated_at: datetime
