from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas import DataUTC, EmpresaResumo

SituacaoTratativa = Literal["EM_ANALISE", "RESOLVIDA"]
TipoProblemaFiscal = Literal["CFOP_SAIDA", "CFOP_ENTRADA", "CANCELADA", "ENTRADA_OUTRA_EMPRESA"]


class _DoServico(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Tratativa(_DoServico):
    situacao: SituacaoTratativa
    usuario_nome: str
    observacao: str
    created_at: DataUTC


class TratativaRegistrada(Tratativa):
    id: int


class NovaTratativa(BaseModel):
    situacao: SituacaoTratativa
    observacao: str = Field(min_length=3, max_length=2000)


class TransferenciaRefControle(_DoServico):
    id: int
    numero_nota: str | None
    origem: EmpresaResumo
    destino: EmpresaResumo | None
    status: str | None
    data_criacao: DataUTC | None
    valor_total: Decimal | None = Field(description="Valor contábil da nota de saída.")
    usuario_emissao: str | None = Field(description="Quem emitiu a nota de saída no ERP.")
    tratativa: Tratativa | None = Field(description="Última tratativa registrada.")


class ExecucaoAnomalias(_DoServico):
    concluida_em: DataUTC
    status: Literal["sucesso", "sem_historico", "erro"]
    notas_treino: int
    notas_avaliadas: int
    notas_sinalizadas: int
    mensagem: str | None


class AnomaliaRef(BaseModel):
    transferencia: TransferenciaRefControle
    score: float = Field(description="Quanto maior, mais fora do padrão. Não é probabilidade.")
    limiar: float
    motivos: list[str] = Field(description="Do que mais pesou para o que menos pesou.")
    avaliada_em: DataUTC


class PainelAnomalias(BaseModel):
    execucao: ExecucaoAnomalias | None = Field(description="Última rodada do detector.")
    analisadas: int = Field(description="Notas do período com score.")
    sinalizadas: int
    lista: list[AnomaliaRef] = Field(description="Até 50, da mais fora do padrão para a menos.")


class TransitoDestino(_DoServico):
    empresa: EmpresaResumo | None = Field(description="Destino; nulo = fora das empresas.")
    quantidade: int
    valor: Decimal
    mais_antiga: DataUTC | None


class Rota(_DoServico):
    origem: EmpresaResumo
    destino: EmpresaResumo
    prazo_horas: int
    prazo_padrao: bool = Field(description="Sem prazo cadastrado para a rota: vale o padrão.")
    enviadas: int
    recebidas: int
    pendentes: int
    fora_do_prazo: int
    divergentes: int
    valor_enviado: Decimal
    tempo_medio_horas: float | None


class ItemDivergente(_DoServico):
    id_produto: str
    descricao: str | None
    enviada: Decimal
    recebida: Decimal
    diferenca: Decimal = Field(description="Enviada − recebida. Negativa = entrou a mais.")
    valor_diferenca: Decimal | None = Field(
        description="Diferença × valor unitário da saída (ou custo gerencial). Nulo sem preço."
    )
    sem_saida: bool = Field(description="Produto que entrou sem estar na nota de saída.")


class Divergencia(_DoServico):
    transferencia: TransferenciaRefControle
    itens: list[ItemDivergente]
    valor_diferenca: Decimal


class ProblemaFiscal(_DoServico):
    transferencia: TransferenciaRefControle
    tipo: TipoProblemaFiscal
    detalhe: str


class Emissor(_DoServico):
    usuario: str
    enviadas: int
    fora_do_prazo: int
    divergentes: int
    problemas_fiscais: int


class ResumoControle(_DoServico):
    em_transito_quantidade: int = Field(description="Pendentes agora, de qualquer data.")
    em_transito_valor: Decimal
    fora_do_prazo: int
    divergentes: int
    valor_divergencia: Decimal
    problemas_fiscais: int
    sem_tratativa: int = Field(
        description="Fora do prazo, divergentes ou com problema fiscal sem tratativa RESOLVIDA."
    )


class FiltroControle(BaseModel):
    empresa: str | None
    data_inicial: date | None
    data_final: date | None


class PainelControle(_DoServico):
    filtros: FiltroControle
    resumo: ResumoControle
    em_transito: list[TransitoDestino]
    rotas: list[Rota]
    divergencias: list[Divergencia] = Field(description="Até 50, maior valor primeiro.")
    fiscal: list[ProblemaFiscal] = Field(description="Até 50, mais recentes primeiro.")
    emissores: list[Emissor]
    prazo_padrao_horas: int
    cfops_saida: list[str]
    cfops_entrada: list[str]


class PrazoRota(BaseModel):
    origem: str = Field(examples=["01"])
    destino: str = Field(examples=["02"])
    horas: int | None = Field(ge=1, le=720, description="Nulo = volta ao prazo padrão.")


class PrazosRota(BaseModel):
    prazo_padrao_horas: int
    prazos: list[PrazoRota]


class LimitesPendencia(BaseModel):
    horas_atencao: int = Field(description="Sem entrada há mais disto: atenção (aviso).")
    horas_critico: int = Field(description="Sem entrada há mais disto: crítico.")
    definido_por: str | None = Field(description="Quem mudou na tela; null: padrão (24 h e 48 h).")
    atualizado_em: DataUTC | None


class NovosLimitesPendencia(BaseModel):
    horas_atencao: int = Field(ge=1, le=719, examples=[24])
    horas_critico: int = Field(ge=2, le=720, examples=[48])
