

import type {
  EmpresaResumo,
  IndicadoresPorEmpresa,
  PaginaParcelas,
  PaginaTransferencias,
  ResumoFinanceiro,
  PontoIndicadores,
  ResumoDashboard,
  ResumoVendas,
  Transferencia,
  TransferenciaDetalhe,
} from "../types/api";

export const empresa = (codigo: string): EmpresaResumo => ({
  id: Number(codigo),
  codigo,
  nome: `Empresa ${codigo}`,
});

export function transferencia(parcial: Partial<Transferencia> = {}): Transferencia {
  return {
    id: 1,
    id_erp: "DEMO-TRF-0001",
    status: "PENDENTE",
    empresa_origem: empresa("01"),
    empresa_destino: empresa("02"),
    data_criacao: "2026-09-20T15:00:00Z",
    data_processamento: null,
    quantidade_itens: 2,
    numero_nota: null,
    chave_nfe: null,
    coi: "8040",
    coi_entrada: null,
    problemas_coi: [],
    valor_total: null,
    usuario_emissao: null,
    situacao_coi: "AGUARDANDO",
    etapas: [
      { chave: "criada", rotulo: "Saída emitida", estado: "concluida", momento: "2026-09-20T15:00:00Z", detalhe: null },
      { chave: "processamento", rotulo: "Entrada no destino", estado: "atual", momento: null, detalhe: "Aguardando a entrada" },
      { chave: "coi", rotulo: "COIs conferidos", estado: "pendente", momento: null, detalhe: null },
      { chave: "concluida", rotulo: "Concluída", estado: "pendente", momento: null, detalhe: null },
    ],
    ...parcial,
  };
}


export function transferenciaCoiErrado(parcial: Partial<Transferencia> = {}): Transferencia {
  return transferencia({
    id: 4,
    id_erp: "DEMO-TRF-0004",
    status: "PROCESSADA",
    data_processamento: "2026-09-20T17:00:00Z",
    coi_entrada: "7163",
    problemas_coi: ["nota de entrada sem COI"],
    situacao_coi: "ERRADO",
    etapas: [
      { chave: "criada", rotulo: "Saída emitida", estado: "concluida", momento: "2026-09-20T15:00:00Z", detalhe: null },
      { chave: "processamento", rotulo: "Entrada no destino", estado: "concluida", momento: "2026-09-20T17:00:00Z", detalhe: null },
      {
        chave: "coi",
        rotulo: "COIs conferidos",
        estado: "falha",
        momento: null,
        detalhe: "nota de entrada sem COI",
      },
      { chave: "concluida", rotulo: "Concluída", estado: "pendente", momento: null, detalhe: null },
    ],
    ...parcial,
  });
}

export function pagina(itens: Transferencia[], parcial: Partial<PaginaTransferencias> = {}): PaginaTransferencias {
  return {
    total: itens.length,
    pagina: 1,
    tamanho_pagina: 20,
    total_paginas: itens.length ? 1 : 0,
    itens,
    ...parcial,
  };
}

export function detalhe(parcial: Partial<TransferenciaDetalhe> = {}): TransferenciaDetalhe {
  return {
    ...transferencia({ status: "PROCESSADA", data_processamento: "2026-09-21T10:00:00Z" }),
    created_at: "2026-09-20T15:01:00Z",
    updated_at: "2026-09-21T10:01:00Z",
    valor_total: "1520.40",
    usuario_emissao: "OPERADOR CAIXA",
    itens: [
      {
        id: 10,
        id_produto_erp: "DEMO-PROD-001",
        codigo_produto: "001",
        descricao_produto: "Produto A",
        quantidade_solicitada: "36.0000",
        quantidade_processada: "35.0000",
        divergente: true,
        valor_total: "720.00",
        cfop_saida: "5152",
        cfop_entrada: "1152",
      },
      {
        id: 11,
        id_produto_erp: "DEMO-PROD-002",
        codigo_produto: "002",
        descricao_produto: "Produto B",
        quantidade_solicitada: "2.5000",
        quantidade_processada: "2.5000",
        divergente: false,
        valor_total: "800.40",
        cfop_saida: "5152",
        cfop_entrada: "1152",
      },
    ],
    ...parcial,
  };
}

export function resumo(parcial: Partial<ResumoDashboard> = {}): ResumoDashboard {
  return {
    gerado_em: "2026-09-26T12:00:00Z",
    filtro: { empresa: null, data_inicial: null, data_final: null, comparar_inicial: null, comparar_final: null },
    transferencias: { total: 36, processadas: 26, pendentes: 5, com_erro: 5 },
    periodo: null,
    comparacao: null,
    situacao_atual: { pendentes: 5, pendentes_atrasadas: 4, com_erro: 5 },
    empresas_ativas: 6,
    ultima_sincronizacao: {
      tipo: "transferencias",
      status: "parcial",
      inicio: "2026-09-26T10:00:00Z",
      fim: "2026-09-26T10:01:00Z",
      mensagem_erro: null,
      empresa: empresa("03"),
    },
    eventos_por_severidade: { INFO: 4, WARNING: 7, ERROR: 7, CRITICAL: 3 },
    status_por_empresa: [],
    limites_pendencia: { horas_atencao: 24, horas_critico: 48 },
    ...parcial,
  };
}

export function pontoIndicadores(chave: string, parcial: Partial<PontoIndicadores> = {}): PontoIndicadores {
  return {
    chave,
    a_receber: 0,
    recebidas: 0,
    taxa_entrada: null,
    tempo_medio_entrada_horas: null,
    enviadas: 0,
    itens_enviados: 0,
    aguardando_destino: 0,
    coi_errado: 0,
    ...parcial,
  };
}


export function indicadores(parcial: Partial<IndicadoresPorEmpresa> = {}): IndicadoresPorEmpresa {
  return {
    gerado_em: "2026-09-30T12:00:00Z",
    granularidade: "dia",
    data_inicial: "2026-09-28",
    data_final: "2026-09-30",
    empresas: [
      {
        empresa: empresa("01"),
        totais: pontoIndicadores("total", {
          a_receber: 1,
          recebidas: 3,
          taxa_entrada: 75,
          tempo_medio_entrada_horas: 2.5,
          enviadas: 6,
          itens_enviados: 15,
          aguardando_destino: 1,
          coi_errado: 1,
        }),
        serie: [
          pontoIndicadores("2026-09-28", { enviadas: 2, recebidas: 1, itens_enviados: 5, taxa_entrada: 100, tempo_medio_entrada_horas: 2 }),
          pontoIndicadores("2026-09-29", { recebidas: 2, a_receber: 1, taxa_entrada: 66.7, tempo_medio_entrada_horas: 3 }),
          pontoIndicadores("2026-09-30", {
            enviadas: 4,
            aguardando_destino: 1,
            coi_errado: 1,
            itens_enviados: 10,
          }),
        ],
      },
    ],
    ...parcial,
  };
}


export function respostaJson(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const totaisVendas = (faturamento: string, notas: number, devolucoes: string | null = "0") => ({
  faturamento,
  notas,
  ticket_medio: notas ? (Number(faturamento) / notas).toFixed(2) : null,
  quantidade: "1520.5000",
  desconto: "320.10",
  devolucoes,
  faturamento_liquido: (Number(faturamento) - Number(devolucoes ?? 0)).toFixed(2),
});

export const vendedorVendas = (id: string, faturamento: string, comparacao: string | null, abaixo: boolean, nome: string | null = null) => ({
  id_vendedor: id,
  nome,
  empresas: [empresa("1")],
  faturamento,
  notas: 100,
  ticket_medio: (Number(faturamento) / 100).toFixed(2),
  faturamento_comparacao: comparacao,
  abaixo_da_media: abaixo,
});


export function resumoVendas(parcial: Partial<ResumoVendas> = {}): ResumoVendas {
  return {
    gerado_em: "2026-10-10T12:00:00Z",
    filtro: {
      empresa: null,
      data_inicial: "2026-10-10",
      data_final: "2026-10-10",
      comparar_inicial: "2026-10-03",
      comparar_final: "2026-10-03",
      canal: null,
      dias: null,
    },
    totais: totaisVendas("125430.90", 300, "5430.90"),
    comparacao: totaisVendas("100000.00", 250, "0"),
    granularidade: "dia",
    serie: [{ chave: "2026-10-10", faturamento: "125430.90", notas: 300, quantidade: "1520.5000", devolucoes: "5430.90" }],
    por_canal: [
      { canal: "faturamento", rotulo: "Faturamento logística", faturamento: "100000.00", notas: 50, quantidade: "1000" },
      { canal: "balcao", rotulo: "Balcão (NFC-e)", faturamento: "25430.90", notas: 250, quantidade: "520.5" },
    ],
    por_categoria: [
      { categoria: "MATERIAL DE CONSTRUCAO", faturamento: "90000.00", notas: 120, quantidade: "1200" },
      { categoria: "TINTAS", faturamento: "35430.90", notas: 180, quantidade: "320.5" },
    ],
    por_empresa: [{ empresa: empresa("1"), faturamento: "125430.90", notas: 300, ticket_medio: "418.10" }],
    produtos: [
      { id_produto: "12636", id_subproduto: "12637", descricao: "CIMENTO FICTICIO 50KG", quantidade: "800.0000", faturamento: "40000.00" },
    ],
    cobertura: { desde: "2025-09-06", ate: "2026-10-10", atualizado_em: "2026-10-10T11:55:00Z" },
    vendedores: {
      media_faturamento: "41810.30",
      vendedores: [
        vendedorVendas("633", "80000.00", "60000.00", false, "MARIA DA SILVA SOUZA"),
        vendedorVendas("22", "30000.00", "30000.00", true, "JOAO DOS SANTOS"),
        vendedorVendas("16055", "15430.90", "0", true),
      ],
      sem_vendedor_faturamento: "120.00",
      sem_vendedor_notas: 2,
    },
    formas_pagamento: [
      { forma: "PIX TEF", valor: "60000.00", parcelas: 120 },
      { forma: "CARTAO CREDITO TEF", valor: "40000.00", parcelas: 80 },
    ],
    ...parcial,
  };
}


export function resumoFinanceiro(parcial: Partial<ResumoFinanceiro> = {}): ResumoFinanceiro {
  return {
    gerado_em: "2026-10-10T12:00:00Z",
    filtro: { empresa: null, data_inicial: "2026-10-10", data_final: "2026-10-10" },
    vendas: {
      valor: "100000.00",
      valor_pago: "90000.00",
      valor_pendente: "10000.00",
      parcelas: 200,
      formas: [
        { forma: "PIX TEF", valor: "60000.00", valor_pago: "60000.00", valor_pendente: "0.00", parcelas: 120 },
        { forma: "CARTAO CREDITO TEF", valor: "40000.00", valor_pago: "30000.00", valor_pendente: "10000.00", parcelas: 80 },
      ],
    },
    recebidos: {
      total: "95000.00",
      de_vendas_anteriores: "5000.00",
      de_boletos: "4000.00",
      das_vendas_do_periodo: "90000.00",
      outros_anteriores: "1000.00",
      juros: "12.50",
      titulos: 190,
      formas: [
        { forma: "PIX TEF", valor: "60000.00", titulos: 120 },
        { forma: "CARTAO CREDITO TEF", valor: "30000.00", titulos: 60 },
        { forma: "BOLETO BANCO EXEMPLO", valor: "5000.00", titulos: 10 },
      ],
    },
    cobertura: { desde: "2026-01-01", ate: "2026-10-10", atualizado_em: "2026-10-10T11:55:00Z" },
    ...parcial,
  };
}

export function paginaParcelas(
  sobrescrever: Partial<PaginaParcelas> = {},
): PaginaParcelas {
  return {
    total: 2,
    pagina: 1,
    tamanho_pagina: 50,
    total_paginas: 1,
    valor: "350.00",
    valor_pago: "200.00",
    valor_pendente: "150.00",
    itens: [
      {
        empresa: "1",
        empresa_nome: "Matriz",
        documento: "900123",
        titulo: "45",
        parcela: "1",
        forma: "BOLETO BANCO EXEMPLO (NOVO)",
        dia_lancamento: "2026-10-01",
        vencimento: "2026-10-31",
        dia_pagamento: "2026-11-05",
        valor: "200.00",
        valor_pago: "200.00",
        valor_pendente: "0.00",
        juros: "0.00",
        desconto: "0.00",
        situacao: "PAGA",
      },
      {
        empresa: "1",
        empresa_nome: "Matriz",
        documento: "900123",
        titulo: "45",
        parcela: "2",
        forma: "BOLETO BANCO EXEMPLO (NOVO)",
        dia_lancamento: "2026-10-01",
        vencimento: "2026-11-30",
        dia_pagamento: null,
        valor: "150.00",
        valor_pago: "0.00",
        valor_pendente: "150.00",
        juros: "0.00",
        desconto: "0.00",
        situacao: "PENDENTE",
      },
    ],
    ...sobrescrever,
  };
}
