from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

from app.services import pipeline
from app.services.pipeline import SituacaoCoi


def _em_utc(valor: datetime) -> datetime:
    return valor.replace(tzinfo=UTC) if valor.tzinfo is None else valor.astimezone(UTC)


DataUTC = Annotated[datetime, AfterValidator(_em_utc)]


StatusTransferencia = Literal["PENDENTE", "PROCESSADA", "CANCELADA", "ERRO"]
StatusSincronizacao = Literal["em_andamento", "sucesso", "parcial", "erro"]


class ContagemPorSeveridade(BaseModel):
    INFO: int = 0
    WARNING: int = 0
    ERROR: int = 0
    CRITICAL: int = 0


class _DoOrm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Erro(BaseModel):
    detail: str = Field(examples=["Transferência 999 não encontrada."])


RESPOSTAS_PROTEGIDAS: dict[int | str, dict[str, Any]] = {
    401: {"model": Erro, "description": "Token ausente, inválido ou expirado."},
    403: {"model": Erro, "description": "Usuário sem permissão para o módulo."},
}


class HealthLive(BaseModel):
    status: str = Field(examples=["ok"])
    app: str
    env: str


class HealthReady(BaseModel):
    status: str = Field(description="ok | indisponivel", examples=["ok"])
    database: str = Field(description="ok | erro", examples=["ok"])


class EmpresaResumo(_DoOrm):
    id: int
    codigo: str = Field(examples=["01"])
    nome: str = Field(examples=["Empresa Demonstração 01"])


class Empresa(EmpresaResumo):
    id_erp: str | None = Field(description="Identificador da empresa no ERP.")
    bairro: str | None = None
    ativo: bool
    ambiente: str = Field(examples=["development"])
    created_at: DataUTC
    updated_at: DataUTC


class EtapaPipeline(BaseModel):
    chave: Literal["criada", "processamento", "coi", "concluida"]
    rotulo: str = Field(examples=["COIs conferidos"])
    estado: Literal["concluida", "atual", "falha", "pendente"]
    momento: DataUTC | None = Field(description="UTC. Quando a etapa foi cumprida, se conhecido.")
    detalhe: str | None = Field(examples=["COI de saida 8051 nao e da empresa 2 (esperado: 8044)"])


class Transferencia(_DoOrm):
    id: int
    id_erp: str = Field(description="IDPLANILHA da nota de saída no ERP.")
    status: StatusTransferencia | None = Field(
        description=(
            "PENDENTE (sem entrada no destino), PROCESSADA (entrada registrada), "
            "CANCELADA (nota de saída cancelada) ou ERRO."
        ),
        examples=["PENDENTE"],
    )
    empresa_origem: EmpresaResumo
    empresa_destino: EmpresaResumo | None = Field(
        description="Nulo quando o destinatário da nota não é uma das empresas."
    )
    data_criacao: DataUTC | None = Field(description="UTC. Emissão da nota de saída.")
    data_processamento: DataUTC | None = Field(
        description="UTC. Movimento da nota de entrada; nula se ainda não entrou."
    )
    quantidade_itens: int | None
    numero_nota: str | None = Field(description="Número da nota de saída.")
    chave_nfe: str | None = Field(description="Chave da NF-e de saída.")
    coi: str | None = Field(
        description="COI (operação interna) da nota de saída.", examples=["8044"]
    )
    coi_entrada: str | None = Field(
        description="COI da nota de entrada. Nulo = entrada ainda não registrada.",
        examples=["7161"],
    )
    problemas_coi: list[str] = Field(
        description="O que está errado nos COIs; vazio = certo até aqui."
    )
    valor_total: Decimal | None = Field(description="Valor contábil da nota de saída.")
    usuario_emissao: str | None = Field(
        description="Quem emitiu a nota de saída. A nota de entrada não informa o usuário."
    )

    @computed_field(  # type: ignore[prop-decorator]
        description=(
            "ERRADO: há problema de COI (nota não cancelada). CORRETO: sem problema e com "
            "entrada. AGUARDANDO: sem problema até aqui, entrada ainda não registrada."
        )
    )
    @property
    def situacao_coi(self) -> SituacaoCoi:
        return pipeline.situacao_coi(self.status, self.problemas_coi, self.coi_entrada)

    @computed_field(  # type: ignore[prop-decorator]
        description="Etapas: saída emitida, entrada no destino, COIs conferidos, concluída."
    )
    @property
    def etapas(self) -> list[EtapaPipeline]:
        return [
            EtapaPipeline(
                chave=e.chave,
                rotulo=e.rotulo,
                estado=e.estado,
                momento=e.momento,
                detalhe=e.detalhe,
            )
            for e in pipeline.etapas(
                self.status,
                self.problemas_coi,
                self.coi_entrada,
                self.data_criacao,
                self.data_processamento,
            )
        ]


class TransferenciaItem(_DoOrm):
    id: int
    id_produto_erp: str
    codigo_produto: str | None
    descricao_produto: str | None
    quantidade_solicitada: Decimal | None
    quantidade_processada: Decimal | None = Field(description="Nula enquanto não processada.")
    valor_total: Decimal | None = Field(description="Valor do item na nota de saída.")
    cfop_saida: str | None
    cfop_entrada: str | None

    @computed_field(description="Processada e diferente da solicitada.")  # type: ignore[prop-decorator]
    @property
    def divergente(self) -> bool:
        return (
            self.quantidade_processada is not None
            and self.quantidade_solicitada is not None
            and self.quantidade_processada != self.quantidade_solicitada
        )


class TransferenciaDetalhe(Transferencia):
    created_at: DataUTC
    updated_at: DataUTC
    itens: list[TransferenciaItem] = Field(description="Ordenados por id.")


class PaginaTransferencias(BaseModel):
    total: int = Field(description="Total de registros que atendem aos filtros.")
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    itens: list[Transferencia]


class TotaisTransferencias(BaseModel):
    total: int
    processadas: int = Field(description="Status PROCESSADA (sem diferenciar maiúsculas).")
    pendentes: int = Field(description="Status PENDENTE.")
    com_erro: int = Field(description="Status ERRO.")


class Sincronizacao(_DoOrm):
    tipo: str
    status: StatusSincronizacao
    inicio: DataUTC
    fim: DataUTC | None
    mensagem_erro: str | None


class SincronizacaoComEmpresa(Sincronizacao):
    empresa: EmpresaResumo | None = Field(description="Nula em sincronização global.")


class StatusEmpresa(BaseModel):
    empresa: EmpresaResumo
    status: Literal["ok", "atencao", "critico"] = Field(
        description="Regra documentada no README (seção *Status por empresa*)."
    )
    motivos: list[str] = Field(description="Cada condição que levou ao status. Vazia se ok.")
    ultima_sincronizacao: Sincronizacao | None
    pendentes: int = Field(description="PENDENTE com a empresa como origem.")
    pendentes_atrasadas: int = Field(
        description="Das pendentes, criadas há mais que o limite de atenção e até o de crítico."
    )
    pendentes_criticas: int = Field(
        description="Das pendentes, criadas há mais que o limite de crítico."
    )
    com_erro: int = Field(description="ERRO com a empresa como origem.")


class FiltroResumo(BaseModel):
    empresa: EmpresaResumo | None = Field(description="Nula = todas as empresas (consolidado).")
    data_inicial: date | None
    data_final: date | None
    comparar_inicial: date | None
    comparar_final: date | None


class Fluxo(BaseModel):
    criadas: int = Field(description="Transferências criadas no intervalo (data_criacao).")
    processadas: int = Field(
        description="Transferências processadas no intervalo (data_processamento)."
    )
    eventos: int = Field(description="Eventos ocorridos no intervalo (data_evento).")


class SituacaoAtual(BaseModel):
    pendentes: int = Field(description="PENDENTE agora, de qualquer data de criação.")
    pendentes_atrasadas: int = Field(
        description="Das pendentes, criadas há mais que o limite de atenção."
    )
    com_erro: int = Field(description="ERRO agora, de qualquer data de criação.")


class LimitesHoras(BaseModel):
    horas_atencao: int = Field(description="Pendente há mais disto: atenção. Padrão 24.")
    horas_critico: int = Field(description="Pendente há mais disto: crítico. Padrão 48.")


class ResumoDashboard(BaseModel):
    gerado_em: DataUTC = Field(description="Momento de referência dos cálculos (UTC).")
    filtro: FiltroResumo = Field(description="Filtros aplicados, como o backend os entendeu.")
    transferencias: TotaisTransferencias = Field(
        description="Criadas no período (todas, sem período), por status."
    )
    periodo: Fluxo | None = Field(description="Fluxo do período. Nulo sem período.")
    comparacao: Fluxo | None = Field(
        description="O mesmo fluxo no intervalo de comparação. Nulo sem comparação."
    )
    situacao_atual: SituacaoAtual = Field(description="Estado de agora; ignora o período.")
    empresas_ativas: int
    ultima_sincronizacao: SincronizacaoComEmpresa | None = Field(
        description="A sincronização iniciada mais recentemente (da empresa filtrada, se houver)."
    )
    eventos_por_severidade: ContagemPorSeveridade = Field(
        description="Eventos do período por severidade; as 4 severidades sempre presentes.",
        examples=[{"INFO": 4, "WARNING": 7, "ERROR": 7, "CRITICAL": 3}],
    )
    status_por_empresa: list[StatusEmpresa] = Field(
        description="Empresas ativas (só a filtrada, se houver), por código. Ignora o período."
    )
    limites_pendencia: LimitesHoras = Field(
        description="Limites de atenção e crítico em vigor (o ADMIN muda em "
        "PUT /transferencias/limites)."
    )


class PontoIndicadores(BaseModel):
    chave: str = Field(
        description="Balde no fuso TZ: `YYYY-MM-DDTHH` (hora), `YYYY-MM-DD` (dia) ou "
        "`YYYY-MM` (mês). Em `totais`, vale `total`.",
        examples=["2026-10-02"],
    )
    a_receber: int = Field(
        description="Para a empresa (destino), criadas no balde e PENDENTE agora: sem entrada."
    )
    recebidas: int = Field(description="Entradas feitas pela empresa, por data_processamento.")
    taxa_entrada: float | None = Field(
        description="% das notas para a empresa criadas no balde que já tiveram entrada. "
        "Nula sem notas."
    )
    tempo_medio_entrada_horas: float | None = Field(
        description="Média de horas entre a saída e a entrada das recebidas no balde."
    )
    enviadas: int = Field(description="Criadas com a empresa como origem.")
    itens_enviados: int = Field(description="Soma de quantidade_itens das enviadas.")
    aguardando_destino: int = Field(description="Das enviadas no balde, PENDENTE agora.")
    coi_errado: int = Field(
        description="Da empresa (origem ou destino), criadas no balde, com problemas de COI."
    )


class IndicadoresEmpresa(BaseModel):
    empresa: EmpresaResumo
    totais: PontoIndicadores = Field(description="O período inteiro.")
    serie: list[PontoIndicadores] = Field(description="Todos os baldes, inclusive os vazios.")


class IndicadoresPorEmpresa(BaseModel):
    gerado_em: DataUTC
    granularidade: Literal["hora", "dia", "mes"] = Field(
        description="1 dia -> hora; até 62 dias -> dia; acima -> mês."
    )
    data_inicial: date
    data_final: date
    empresas: list[IndicadoresEmpresa] = Field(
        description="Empresas ativas (só a filtrada, se houver), por código."
    )


Severidade = Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
StatusAlerta = Literal["ABERTO", "RESOLVIDO"]


class TransferenciaRef(_DoOrm):
    id: int
    id_erp: str


class Alerta(_DoOrm):
    id: int
    regra: str = Field(examples=["transferencia_atrasada"])
    severidade: Severidade
    status: StatusAlerta
    titulo: str = Field(examples=["Transferência DEMO-0007 pendente há 26h"])
    mensagem: str
    empresa: EmpresaResumo | None
    transferencia: TransferenciaRef | None
    aberto_em: DataUTC
    visto_em: DataUTC = Field(description="Última avaliação em que a situação ainda existia.")
    resolvido_em: DataUTC | None


class PaginaAlertas(BaseModel):
    total: int
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    itens: list[Alerta]


class ResumoAlertas(BaseModel):
    abertos: int
    por_severidade: ContagemPorSeveridade = Field(
        description="Abertos por severidade; todas as severidades presentes."
    )


class FrescorTipo(BaseModel):
    tipo: Literal["transferencias", "estoque", "precos", "vendas", "movimentos_estoque"] = Field(
        examples=["transferencias"]
    )
    intervalo_segundos: int = Field(description="De quanto em quanto tempo a sincronizacao roda.")
    ultima_conclusao: DataUTC | None = Field(
        description="Fim da ultima execucao que concluiu (sucesso ou parcial); nulo = nunca."
    )
    limite_segundos: int = Field(
        description="Acima disto a situacao e ATRASADA; acima do triplo, PARADA."
    )
    situacao: Literal["EM_DIA", "ATRASADA", "PARADA", "NUNCA"]


class Frescor(BaseModel):
    gerado_em: DataUTC
    tipos: list[FrescorTipo]
