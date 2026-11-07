

import type { components } from "./openapi.gen";


export type SempreEnviado<T> = T extends readonly (infer U)[]
  ? SempreEnviado<U>[]
  : T extends object
    ? { [K in keyof T]-?: SempreEnviado<Exclude<T[K], undefined>> }
    : T;
type Gerado<Nome extends keyof components["schemas"]> = SempreEnviado<components["schemas"][Nome]>;

export type DataISO = string;
export type Decimal = string;

export type HealthLive = Gerado<"HealthLive">;

export type EmpresaResumo = Gerado<"EmpresaResumo">;

export type Empresa = Gerado<"Empresa">;


export type SituacaoCoi = "CORRETO" | "ERRADO" | "AGUARDANDO";

export type EstadoEtapa = "concluida" | "atual" | "falha" | "pendente";


export type EtapaPipeline = Gerado<"EtapaPipeline">;


export type StatusTransferencia = "PENDENTE" | "PROCESSADA" | "CANCELADA" | "ERRO";

export type Transferencia = Gerado<"Transferencia">;

export type TransferenciaItem = Gerado<"TransferenciaItem">;

export type TransferenciaDetalhe = Gerado<"TransferenciaDetalhe">;

export type PaginaTransferencias = Gerado<"PaginaTransferencias">;

export type TotaisTransferencias = Gerado<"TotaisTransferencias">;

export type StatusSincronizacao = "em_andamento" | "sucesso" | "parcial" | "erro";

export type Sincronizacao = Gerado<"Sincronizacao">;

export type SincronizacaoComEmpresa = Gerado<"SincronizacaoComEmpresa">;

export type NivelStatusEmpresa = "ok" | "atencao" | "critico";

export type StatusEmpresa = Gerado<"StatusEmpresa">;


export type FiltroResumo = Gerado<"FiltroResumo">;


export type Fluxo = Gerado<"Fluxo">;


export type SituacaoAtual = Gerado<"SituacaoAtual">;

export type ResumoDashboard = Gerado<"ResumoDashboard">;

export type LimitesHoras = Gerado<"LimitesHoras">;


export interface ParamsResumo {
  empresa?: string;
  data_inicial?: string;
  data_final?: string;
  comparar_inicial?: string;
  comparar_final?: string;
}


export interface FiltrosTransferencia {
  empresa_origem: string;
  empresa_destino: string;
  status: string;

  situacao_coi: string;

  emitida_por: string;

  ocorrencia: string;
}

export const FILTROS_VAZIOS: FiltrosTransferencia = {
  empresa_origem: "",
  empresa_destino: "",
  status: "",
  situacao_coi: "",
  emitida_por: "",
  ocorrencia: "",
};


export type OcorrenciaControle = "FORA_DO_PRAZO" | "DIVERGENTE" | "FISCAL" | "SEM_TRATATIVA";


export interface ParamsTransferencias extends Partial<FiltrosTransferencia> {

  empresa?: string;
  data_inicial?: string;
  data_final?: string;
}





export type Severidade = "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type StatusAlerta = "ABERTO" | "RESOLVIDO";

export type Alerta = Gerado<"Alerta">;

export type PaginaAlertas = Gerado<"PaginaAlertas">;

export type ResumoAlertas = Gerado<"ResumoAlertas">;

export interface ParamsAlertas {
  status?: StatusAlerta;
  severidade?: Severidade;
  empresa?: string;
}





export type GranularidadeIndicadores = "hora" | "dia" | "mes";

export type PontoIndicadores = Gerado<"PontoIndicadores">;

export type IndicadoresEmpresa = Gerado<"IndicadoresEmpresa">;

export type IndicadoresPorEmpresa = Gerado<"IndicadoresPorEmpresa">;

export interface ParamsIndicadores {
  empresa?: string;
  data_inicial?: string;
  data_final?: string;
}





export type SituacaoEstoque = "com_saldo" | "sem_saldo" | "negativo" | "com_reserva";
export type OrdenacaoEstoque = "produto" | "maior_saldo" | "menor_saldo" | "menor_cobertura" | "maior_cobertura";

export type StatusCobertura = "ruptura" | "critica" | "baixa" | "adequada" | "excesso" | "sem_giro";

export interface ParamsEstoque {
  produto?: string;

  empresa?: string;

  local?: string;
  situacao?: SituacaoEstoque;
  ordenacao?: OrdenacaoEstoque;
  cobertura?: StatusCobertura;

  fornecedor?: string;

  media?: "vendas" | "baixa";

  so_locais_da_loja?: boolean;

  janela_dias?: number;
}

export interface CoberturaEstoque {

  venda_media_diaria: Decimal | null;

  cobertura_dias: Decimal | null;

  status_cobertura: StatusCobertura | null;

  excecao?: boolean;
}

export type JanelaVendas = Gerado<"JanelaVendas">;

export type ContagemCobertura = Gerado<"ContagemCobertura">;

export type ResumoCobertura = Gerado<"ResumoCobertura">;


export type CoberturaLojas = Gerado<"CoberturaLojas">;
export type CoberturaEmpresa = Gerado<"CoberturaEmpresa">;
export type CoberturaLocal = Gerado<"CoberturaLocal">;


export type ExcecaoCobertura = Gerado<"ExcecaoCobertura">;
export type NovaExcecaoCobertura = Gerado<"NovaExcecaoCobertura">;
export type ResultadoExcecaoCobertura = Gerado<"ResultadoExcecaoCobertura">;
export type ItemPedidoAbastecimento = Gerado<"ItemPedidoAbastecimento">;
export type PedidoAbastecimento = Gerado<"PedidoAbastecimento">;

export interface SaldosEstoque {
  saldo_atual: Decimal | null;
  saldo_reservado: Decimal | null;

  saldo_disponivel: Decimal | null;
}

export type ItemEstoque = Gerado<"ItemEstoque">;

export type PaginaEstoque = Gerado<"PaginaEstoque">;

export type EstoquePorEmpresa = Gerado<"EstoquePorEmpresa">;


export type LocalPerda = Gerado<"LocalPerda">;

export type ResumoEstoque = Gerado<"ResumoEstoque">;

export type LocalEstoque = Gerado<"LocalEstoque">;

export type PrecoEmpresa = Gerado<"PrecoEmpresa">;

export type EmpresaDoProduto = Gerado<"EmpresaDoProduto">;


export type FornecedorDoProduto = Gerado<"FornecedorDoProduto">;

export type FornecedorEstoque = Gerado<"FornecedorEstoque">;

export type ProdutoEstoque = Gerado<"ProdutoEstoque">;






export type CanalVenda = "balcao" | "televendas" | "faturamento";






export type TipoMovimentoEstoque = "entrada_avulsa" | "saida_avulsa" | "balanco";

export type FiltroTipoMovimento = TipoMovimentoEstoque | "avulsas";

export interface ParamsMovimentos {
  data_inicial?: string;
  data_final?: string;
  empresa?: string;
  tipo?: FiltroTipoMovimento;
  produto?: string;
  subproduto?: string;
}


export type MovimentoEstoque = Gerado<"MovimentoEstoque">;


export type ResumoMovimentosDia = Gerado<"ResumoMovimentosDia">;

export type FiltroMovimentos = Gerado<"FiltroMovimentos">;

export type CoberturaMovimentos = Gerado<"CoberturaMovimentos">;

export type PaginaMovimentosEstoque = Gerado<"PaginaMovimentosEstoque">;

export interface ParamsVendas {
  empresa?: string;
  canal?: CanalVenda;
  data_inicial?: string;
  data_final?: string;
  comparar_inicial?: string;
  comparar_final?: string;

  dias?: string;
}

export interface ParamsExportarDescontos {
  data_inicial: string;
  data_final: string;
  empresa?: string;
  canal?: CanalVenda;
}

export type TotaisVendas = Gerado<"TotaisVendas">;

export type PontoVendas = Gerado<"PontoVendas">;

export type VendasPorCanal = Gerado<"VendasPorCanal">;

export type VendasPorCategoria = Gerado<"VendasPorCategoria">;

export type VendasPorEmpresa = Gerado<"VendasPorEmpresa">;

export type VendasPorVendedor = Gerado<"VendasPorVendedor">;

export type RankingVendedores = Gerado<"RankingVendedores">;

export type ProdutoVendido = Gerado<"ProdutoVendido">;


export type FormaPagamento = Gerado<"FormaPagamento">;

export type ResumoVendas = Gerado<"ResumoVendas">;






export type FormaVendida = Gerado<"FormaVendida">;

export type VendasPagas = Gerado<"VendasPagas">;

export type FormaRecebida = Gerado<"FormaRecebida">;


export type Recebidos = Gerado<"Recebidos">;

export type ResumoFinanceiro = Gerado<"ResumoFinanceiro">;

export interface ParamsFinanceiro {
  empresa?: string;
  data_inicial?: string;
  data_final?: string;
}


export type Parcela = Gerado<"Parcela">;

export type PaginaParcelas = Gerado<"PaginaParcelas">;

export type DataParcela = "lancamento" | "pagamento";
export type SituacaoParcela = "todas" | "pagas" | "pendentes";

export interface ParamsParcelas extends ParamsFinanceiro {
  data_por?: DataParcela;
  situacao?: SituacaoParcela;
  forma?: string;
  pagina?: number;
  tamanho_pagina?: number;
}





export type SituacaoTratativa = "EM_ANALISE" | "RESOLVIDA";
export type TipoProblemaFiscal = "CFOP_SAIDA" | "CFOP_ENTRADA" | "CANCELADA" | "ENTRADA_OUTRA_EMPRESA";

export type Tratativa = Gerado<"Tratativa">;

export type TratativaRegistrada = Gerado<"TratativaRegistrada">;

export type TransferenciaRefControle = Gerado<"TransferenciaRefControle">;

export type TransitoDestino = Gerado<"TransitoDestino">;

export type RotaControle = Gerado<"Rota">;

export type ItemDivergente = Gerado<"ItemDivergente">;

export type DivergenciaControle = Gerado<"Divergencia">;

export type ProblemaFiscal = Gerado<"ProblemaFiscal">;

export type EmissorControle = Gerado<"Emissor">;

export type PainelControle = Gerado<"PainelControle">;
export type PainelAnomalias = Gerado<"PainelAnomalias">;

export type PrazoRota = Gerado<"PrazoRota">;

export type PrazosRota = Gerado<"PrazosRota">;


export type LimitesPendencia = Gerado<"LimitesPendencia">;

export type NovosLimitesPendencia = Gerado<"NovosLimitesPendencia">;





export type TipoFrescor = "transferencias" | "estoque" | "precos" | "vendas" | "movimentos_estoque";
export type SituacaoFrescor = "EM_DIA" | "ATRASADA" | "PARADA" | "NUNCA";

export type FrescorTipo = Gerado<"FrescorTipo">;

export type Frescor = Gerado<"Frescor">;







export type CategoriaMovimento =
  | "venda"
  | "devolucao_venda"
  | "compra"
  | "devolucao_compra"
  | "transferencia_entrada"
  | "transferencia_saida"
  | "entrada_avulsa"
  | "saida_avulsa"
  | "balanco"
  | "perda"
  | "uso_consumo"
  | "producao"
  | "bonificacao"
  | "remessa"
  | "outros"
  | "nao_classificado";

export interface ParamsLivro {
  data_inicial?: string;
  data_final?: string;
  empresa?: string;
  categoria?: CategoriaMovimento;
}

export type LinhaLivro = Gerado<"LinhaLivro">;

export type LivroEstoque = Gerado<"LivroEstoque">;


export interface ParamsNotasLivro extends ParamsLivro {
  coi?: number;

  empresa_errada?: boolean;
}

export type NotaLivro = Gerado<"NotaLivro">;

export type PaginaNotasLivro = Gerado<"PaginaNotasLivro">;

export type ItemNotaLivro = Gerado<"ItemNotaLivro">;

export type MovimentoExtrato = Gerado<"MovimentoExtrato">;

export type TotalCategoriaExtrato = Gerado<"TotalCategoriaExtrato">;

export type ExtratoProduto = Gerado<"ExtratoProduto">;






export type TotaisBalanco = Gerado<"TotaisBalanco">;

export type LojaBalanco = Gerado<"LojaBalanco">;

export type AjusteProduto = Gerado<"AjusteProduto">;

export type ParTransferencia = Gerado<"ParTransferencia">;

export type ResumoBalancos = Gerado<"ResumoBalancos">;

export type Recontagem = Gerado<"Recontagem">;

export type MarcaRecontagem = Gerado<"MarcaRecontagem">;





export type TipoAvulsa = "entrada_avulsa" | "saida_avulsa";

export type SituacaoJustificativa = "pendente" | "justificada" | "todas";

export type MotivoAvulsa = Gerado<"MotivoAvulsa">;

export type JustificativaAvulsa = Gerado<"JustificativaAvulsa">;

export type DocumentoAvulso = Gerado<"DocumentoAvulso">;

export type PaginaDocumentosAvulsos = Gerado<"PaginaDocumentosAvulsos">;

export type NovaJustificativaAvulsa = Gerado<"NovaJustificativaAvulsa">;

export type VinculoAvulsa = Gerado<"VinculoAvulsa">;

export type AlertaAvulsa = Gerado<"AlertaAvulsa">;

export type RegraAlerta = Gerado<"RegraAlerta">;

export type CorteAvulsas = Gerado<"CorteAvulsas">;

export type JustificativaEmLote = Gerado<"JustificativaEmLote">;

export type ResultadoLoteJustificativas = Gerado<"ResultadoLoteJustificativas">;

export type CandidatoVinculo = Gerado<"CandidatoVinculo">;


export interface ParamsDocumentosAvulsos extends ParamsLivro {
  tipo?: TipoAvulsa;
  situacao?: SituacaoJustificativa;

  alerta?: string;
}

export type Recontagens = Gerado<"Recontagens">;


export interface ParamsRecontagens extends ParamsLivro {
  mais_de?: number;
  desde?: string;

  marca?: string[];
}





export type CampoAlerta = Gerado<"CampoAlerta">;
export type RegraAlertaConfig = Gerado<"RegraAlertaConfig">;
export type DestinoAlerta = Gerado<"DestinoAlerta">;
export type ConfiguracaoAlertas = Gerado<"ConfiguracaoAlertas">;
export type RegraAlertaEntrada = Gerado<"RegraAlertaEntrada">;
export type ModeloMensagemAlerta = Gerado<"ModeloMensagemAlerta">;
export type VariavelModelo = Gerado<"VariavelModelo">;
export type PreviaModelo = Gerado<"PreviaModelo">;
export type PaginaAtividades = Gerado<"PaginaAtividades">;
export type AtividadeRegistrada = Gerado<"AtividadeRegistrada">;
export type Meta = Gerado<"Meta">;
export type MetaEntrada = Gerado<"MetaEntrada">;
export type ConfiguracaoMetas = Gerado<"ConfiguracaoMetas">;
export type ProgressoMeta = Gerado<"ProgressoMeta">;
export type ProgressoMetas = Gerado<"ProgressoMetas">;
export type VendedorOpcao = Gerado<"VendedorOpcao">;
export type ParametrosEstoqueBaixo = Gerado<"ParametrosEstoqueBaixo">;
export type ParametrosEstoqueBaixoEntrada = Gerado<"ParametrosEstoqueBaixoEntrada">;
export type SituacaoEstoqueBaixo = Gerado<"SituacaoEstoqueBaixo">;
export type DestinoAlertaEntrada = Gerado<"DestinoAlertaEntrada">;
export type MensagemAvulsaEntrada = Gerado<"MensagemAvulsaEntrada">;
export type MensagemAvulsa = Gerado<"MensagemAvulsaSaida">;
export type EnvioMensagemAvulsa = Gerado<"EnvioMensagemAvulsa">;
export type ModeloMensagemAvulsa = Gerado<"ModeloMensagemAvulsaSaida">;
