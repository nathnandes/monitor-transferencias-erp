import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../services/apiClient";
import { hojeNoFuso } from "../../lib/periodo";
import {
  getCoberturaEstoque,
  getCoberturaLojas,
  getExcecoesCobertura,
  incluirExcecaoCobertura,
  removerExcecaoCobertura,
  getPedidoAbastecimento,
  getEstoque,
  getBalancos,
  getExtratoProduto,
  getItensNotaLivro,
  getLivroEstoque,
  getMovimentosEstoque,
  getNotasLivro,
  getProdutoEstoque,
  getRecontagens,
  getFornecedoresEstoque,
  getResumoEstoque,
  getDocumentosAvulsos,
  justificarAvulsa,
  justificarAvulsasEmLote,
  definirCorteAvulsas,
  getCandidatosVinculo,
  relacionarAvulsas,
  desfazerVinculo,
} from "../../services/estoqueService";
import { empresa } from "../../test/factories";
import { authFalso, renderComSessao, usuarioTeste } from "../../test/sessao";
import type {
  CoberturaLojas,
  ExtratoProduto,
  ItemEstoque,
  ItemPedidoAbastecimento,
  LivroEstoque,
  MovimentoEstoque,
  PaginaNotasLivro,
  PaginaEstoque,
  PaginaMovimentosEstoque,
  ProdutoEstoque,
  PaginaDocumentosAvulsos,
  Recontagens,
  ResumoBalancos,
  ResumoCobertura,
  ResumoEstoque,
} from "../../types/api";
import { EstoquePage, TITULO_ESTOQUE } from "./EstoquePage";

function itemPedido(campos: Partial<ItemPedidoAbastecimento> = {}): ItemPedidoAbastecimento {
  return {
    id_produto: "1",
    id_subproduto: "1",
    descricao: null,
    marca: "MARCA",
    status_cobertura: "ruptura",
    saldo_loja: "0.000",
    venda_media_diaria: "2.000",
    cobertura_dias: "0.0",
    necessidade: "60.000",
    quantidade: "60.000",
    disponivel_deposito: "100.000",
    ...campos,
  };
}

vi.mock("../../services/estoqueService", () => ({
  getEstoque: vi.fn(),
  getBalancos: vi.fn(),
  getCoberturaEstoque: vi.fn(),
  getCoberturaLojas: vi.fn(),
  getExcecoesCobertura: vi.fn(),
  incluirExcecaoCobertura: vi.fn(),
  removerExcecaoCobertura: vi.fn(),
  getPedidoAbastecimento: vi.fn(),
  getExtratoProduto: vi.fn(),
  getLivroEstoque: vi.fn(),
  getNotasLivro: vi.fn(),
  getItensNotaLivro: vi.fn(),
  getFornecedoresEstoque: vi.fn(),
  getResumoEstoque: vi.fn(),
  getProdutoEstoque: vi.fn(),
  getMovimentosEstoque: vi.fn(),
  getRecontagens: vi.fn(),
  getDocumentosAvulsos: vi.fn(),
  justificarAvulsa: vi.fn(),
  justificarAvulsasEmLote: vi.fn(),
  definirCorteAvulsas: vi.fn(),
  getCandidatosVinculo: vi.fn(),
  relacionarAvulsas: vi.fn(),
  desfazerVinculo: vi.fn(),
}));

function item(parcial: Partial<ItemEstoque> = {}): ItemEstoque {
  return {
    id_produto: "9798",
    id_subproduto: "9798",
    saldo_atual: "188525.000",
    saldo_reservado: "0.000",
    saldo_disponivel: "188525.000",
    empresas_com_estoque: 5,
    excecao: false,
    descricao: "CAFE FICTICIO 500G",
    preco_varejo_min: "12.900000",
    preco_varejo_max: "13.500000",
    custo_gerencial: "8.123456",
    valor_custo: "1222333.155",
    venda_media_diaria: "1250.500",
    cobertura_dias: "150.8",
    status_cobertura: "excesso",
    fabricante: "MARCA FICTICIA",
    fornecedor: "FORNECEDOR FICTICIO LTDA",
    ...parcial,
  };
}

function paginaDe(itens: ItemEstoque[], parcial: Partial<PaginaEstoque> = {}): PaginaEstoque {
  return {
    total: itens.length,
    pagina: 1,
    tamanho_pagina: 50,
    total_paginas: itens.length ? 1 : 0,
    atualizado_em: "2026-10-07T18:10:50Z",
    janela: JANELA,
    tem_vendas: true,
    itens,
    ...parcial,
  };
}

const JANELA = { inicio: "2026-09-19", fim: "2026-10-18", dias: 30 };

const COBERTURA: ResumoCobertura = {
  janela: JANELA,
  tem_vendas: true,
  produtos: { ruptura: 327, critica: 107, baixa: 137, adequada: 1399, excesso: 5237, sem_giro: 7603 },
};

const zerada = { ruptura: 0, critica: 0, baixa: 0, adequada: 0, excesso: 0, sem_giro: 0 };
const COBERTURA_LOJAS: CoberturaLojas = {
  janela: JANELA,
  empresas: [
    {
      empresa: empresa("1"),
      tem_vendas: true,
      excecoes: 2,
      desconsiderados: [
        { id_local: "21", descricao: "AVARIAS LOJA MATRIZ" },
        { id_local: "32", descricao: "PISO" },
      ],
      produtos: { ruptura: 1299, critica: 482, baixa: 350, adequada: 1251, excesso: 1629, sem_giro: 5919 },
      locais: [
        {
          id_local: "1",
          descricao: "LOJA MATRIZ",
          produtos_com_saldo: 9465,
          produtos: { ruptura: 1356, critica: 465, baixa: 345, adequada: 1223, excesso: 1622, sem_giro: 5798 },
          somados: [
            { id_local: "8", descricao: "DEPOSITO 03" },
            { id_local: "9", descricao: "DEPOSITO 04" },
          ],
        },
        {
          id_local: "14",
          descricao: "MOSTRUARIO LOJA MATRIZ",
          produtos_com_saldo: 82,
          produtos: { ruptura: 134, critica: 15, baixa: 8, adequada: 10, excesso: 0, sem_giro: 49 },
          somados: [],
        },
        {
          id_local: "33",
          descricao: "LOJA CENTRO",
          produtos_com_saldo: 0,
          produtos: { ...zerada, ruptura: 1475 },
          somados: [],
        },
      ],
    },
    {
      empresa: empresa("4"),
      tem_vendas: false,
      excecoes: 0,
      desconsiderados: [],
      produtos: zerada,
      locais: [{ id_local: "2", descricao: "DEPOSITO 01", produtos_com_saldo: 4147, produtos: zerada, somados: [] }],
    },
  ],
};

const RESUMO: ResumoEstoque = {
  produtos: 20664,
  produtos_com_saldo: 14691,
  produtos_negativos: 54,
  produtos_com_reserva: 437,
  atualizado_em: "2026-10-07T18:10:50Z",
  ultima_sincronizacao: {
    tipo: "estoque",
    status: "sucesso",
    inicio: "2026-10-07T18:10:04Z",
    fim: "2026-10-07T18:10:50Z",
  },
  por_empresa: [
    { empresa: empresa("1"), produtos_com_saldo: 9227, linhas: 45403, valor_custo: "1800000.10" },
    { empresa: empresa("2"), produtos_com_saldo: 6949, linhas: 18798, valor_custo: "700000.455" },
  ],
  valor_custo: "2500000.555",
  linhas_sem_custo: 3,
  precos_atualizados_em: "2026-10-07T18:30:00Z",
  locais_perda: [
    { empresa: empresa("6"), id_local: "40", descricao: "LOCAL AVARIA", motivo: "Avaria", produtos: 1234, valor: "1111111.00" },
  ],
};

const PRODUTO: ProdutoEstoque = {
  id_produto: "9798",
  id_subproduto: "9798",
  saldo_atual: "15.000",
  saldo_reservado: "1.000",
  saldo_disponivel: "14.000",
  descricao: "CAFE FICTICIO 500G",
  fabricante: "MARCA FICTICIA",
  empresas_com_estoque: 1,
  atualizado_em: "2026-10-07T18:10:50Z",
  venda_media_diaria: "2.000",
  cobertura_dias: "7.0",
  status_cobertura: "baixa",
  janela: JANELA,
  fornecedores: [
    {
      nome: "FORNECEDOR FICTICIO LTDA",
      cnpj: "11222333000181",
      compras: 3,
      quantidade: "120.0000",
      ultima_compra: "2026-10-02",
      ultima_empresa: empresa("1"),
      custo_ultima: "7.5000",
    },
  ],
  empresas: [
    {
      empresa: empresa("1"),
      saldo_atual: "15.000",
      saldo_reservado: "1.000",
      saldo_disponivel: "14.000",
      venda_media_diaria: "2.000",
      cobertura_dias: "7.0",
      status_cobertura: "baixa",
      preco: {
        preco_varejo: "12.900000",
        preco_promocao_varejo: "0.000000",
        inicio_promocao_varejo: null,
        fim_promocao_varejo: null,
        preco_atacado: "0.000000",
        preco_promocao_atacado: "0.000000",
        custo_reposicao: "8.500000",
        custo_gerencial: "8.123456",
        custo_nota_fiscal: "8.300000",
        data_alteracao_erp: "2026-10-07T17:00:00Z",
        sincronizado_em: "2026-10-07T18:30:00Z",
      },
      valor_custo: "121.85184",
      locais: [
        {
          id_local_estoque: "3",
          descricao_local_estoque: "DEPOSITO FUNDOS",
          descricao_lote: "",
          inativo_erp: false,
          saldo_atual: "15.000",
          saldo_reservado: "1.000",
          saldo_disponivel: "14.000",
          data_alteracao_erp: "2026-10-07T17:00:00Z",
          sincronizado_em: "2026-10-07T18:10:50Z",
          perda: null,
        },
        {
          id_local_estoque: "40",
          descricao_local_estoque: "LOCAL AVARIA",
          descricao_lote: "",
          inativo_erp: false,
          saldo_atual: "99.000",
          saldo_reservado: "0.000",
          saldo_disponivel: "99.000",
          data_alteracao_erp: "2026-10-07T17:00:00Z",
          sincronizado_em: "2026-10-07T18:10:50Z",
          perda: "Avaria",
        },
      ],
    },
  ],
};

function movimento(parcial: Partial<MovimentoEstoque> = {}): MovimentoEstoque {
  return {
    id: 1,
    empresa: empresa("1"),
    dia: "2026-10-17",
    tipo: "balanco",
    coi: 2000,
    id_planilha: "B1",
    sequencia: "1",
    id_produto: "9798",
    id_subproduto: "9798",
    descricao: "CAFE FICTICIO 500G",
    quantidade: "-3.0000",
    valor: "-30.0000",
    ...parcial,
  };
}

const MOVIMENTOS: PaginaMovimentosEstoque = {
  total: 2,
  pagina: 1,
  tamanho_pagina: 50,
  total_paginas: 1,
  filtro: { data_inicial: null, data_final: null, empresa: null, tipo: null, produto: null, subproduto: null },
  cobertura: { desde: "2026-10-01", ate: "2026-10-17", atualizado_em: "2026-10-17T12:00:00Z" },
  itens: [
    movimento(),
    movimento({ id: 2, dia: "2026-10-16", tipo: "entrada_avulsa", coi: 80, id_planilha: "E1", quantidade: "5.0000", valor: "50.0000" }),
  ],
  resumo: [
    {
      empresa: empresa("1"),
      dia: "2026-10-17",
      tipo: "balanco",
      itens: 3,
      quantidade: "2.0000",
      valor: "-7.0000",
      falta_itens: 1,
      falta_quantidade: "-3.0000",
      falta_valor: "-30.0000",
      sobra_itens: 2,
      sobra_quantidade: "5.0000",
      sobra_valor: "23.0000",
    },
    {
      empresa: empresa("1"),
      dia: "2026-10-16",
      tipo: "entrada_avulsa",
      itens: 1,
      quantidade: "5.0000",
      valor: "50.0000",
      falta_itens: null,
      falta_quantidade: null,
      falta_valor: null,
      sobra_itens: null,
      sobra_quantidade: null,
      sobra_valor: null,
    },
  ],
};

const LIVRO: LivroEstoque = {
  data_inicial: "2026-10-13",
  data_final: "2026-10-19",
  dias_sem_leitura: 2,
  linhas: [
    { empresa: empresa("1"), coi: 11, operacao: "COMPRA DE MERCADORIA", categoria: "compra", afeta: true, documentos: 4, itens: 9, valor: "1500.00" },
    { empresa: empresa("1"), coi: 8300, operacao: "Venda de Mercadoria ECF", categoria: "venda", afeta: true, documentos: 30, itens: 80, valor: "-900.50" },
    { empresa: empresa("1"), coi: 3000, operacao: "Pedido de Venda Gerencial", categoria: "venda", afeta: null, documentos: 5, itens: 12, valor: "-300.00" },
  ],
};

const NOTAS: PaginaNotasLivro = {
  total: 3,
  pagina: 1,
  tamanho_pagina: 25,
  total_paginas: 1,
  data_inicial: "2026-10-13",
  data_final: "2026-10-19",
  notas: [
    {
      empresa: empresa("1"), id_planilha: "8389517", numero: "4521", dia: "2026-10-19", momento: "2026-10-19T17:50:15Z",
      usuario: "ANTONIA", coi: 8300, operacao: "Venda de Mercadoria ECF", categoria: "venda", afeta: true, itens: 2, valor: "-90.00",
      destinatario: "CLIENTE FICTICIO", destino_empresa: null, empresa_errada: false,
    },
    {
      empresa: empresa("1"), id_planilha: "8193207", numero: "213786", dia: "2026-10-18", momento: "2026-10-18T13:28:16Z",
      usuario: "BEATRIZ", coi: 8038, operacao: "SAIDA MERC. EPI UNIFORME FARDAMENTO", categoria: "uso_consumo", afeta: true,
      itens: 1, valor: "-45.55", destinatario: "EMPRESA FICTICIA 5", destino_empresa: "5", empresa_errada: true,
    },
    {
      empresa: empresa("1"), id_planilha: "8385743", numero: null, dia: "2026-10-18", momento: null,
      usuario: null, coi: 80, operacao: "Entrada Avulsa de Estoque", categoria: "entrada_avulsa", afeta: true, itens: 1, valor: "25.00",
      destinatario: null, destino_empresa: null, empresa_errada: false,
    },
  ],
};

const EXTRATO: ExtratoProduto = {
  empresa: empresa("1"),
  id_produto: "9798",
  id_subproduto: "9798",
  descricao: "CAFE FICTICIO 500G",
  data_inicial: "2026-09-20",
  data_final: "2026-10-19",
  saldo_atual: "15.000",
  saldo_inicial: "8.000",
  saldo_final: "15.000",
  entradas: "12.0000",
  saidas: "-5.0000",
  por_categoria: [{ categoria: "compra", afeta: true, itens: 1, quantidade: "12.0000" }],
  total_itens: 2,
  limite: 1000,
  dias_sem_leitura: [],
  itens: [
    { dia: "2026-10-18", coi: 8300, operacao: "Venda ECF", categoria: "venda", afeta: true, id_planilha: "V1", sequencia: "1", quantidade: "-5.0000", valor: "-50", saldo_fim_dia: "15.000" },
    { dia: "2026-10-10", coi: 11, operacao: "COMPRA", categoria: "compra", afeta: true, id_planilha: "C1", sequencia: "1", quantidade: "12.0000", valor: "7120", saldo_fim_dia: "20.000" },
  ],
};

const BALANCOS: ResumoBalancos = {
  data_inicial: "2026-07-22",
  data_final: "2026-10-19",
  totais: { perda: "-1000.00", ganho: "400.00", resultado: "-600.00", produtos_com_falta: 3, produtos_com_sobra: 2, itens: 9, balancos: 1 },
  por_loja: [
    { empresa: empresa("1"), perda: "-1000.00", ganho: "400.00", resultado: "-600.00", produtos_com_falta: 3, produtos_com_sobra: 2, itens: 9, balancos: 1 },
  ],
  eventos: [MOVIMENTOS.resumo[0]!],
  maiores_perdas: [
    { empresa: empresa("1"), id_produto: "23569", id_subproduto: "23569", descricao: "SELANTE", quantidade: "-10", valor: "-700.00" },
  ],
  maiores_ganhos: [],
  transferencias_provaveis: [
    {
      id_produto: "1194", id_subproduto: "1194", descricao: "THINNER 5L",
      loja_falta: empresa("1"), quantidade_falta: "-5", loja_sobra: empresa("2"), quantidade_sobra: "4",
      quantidade: "4", valor: "250.00",
    },
  ],
  valor_transferencias_provaveis: "250.00",
  locais_perda: [
    { empresa: empresa("6"), id_local: "40", descricao: "LOCAL AVARIA", motivo: "Avaria", produtos: 1234, valor: "1111111.00" },
  ],
};

const DOCUMENTOS_AVULSOS: PaginaDocumentosAvulsos = {
  data_inicial: "2026-10-22",
  data_final: "2026-10-28",
  justificar_desde: "2026-10-01",
  situacao: "pendente",
  pagina: 1,
  tamanho_pagina: 50,
  total: 1,
  total_paginas: 1,
  documentos: [
    {
      empresa: empresa("1"), id_planilha: "8403635", dia: "2026-10-28", tipo: "saida_avulsa", itens: 2,
      quantidade: "-3", valor: "-51.00", id_produto: "28142", id_subproduto: "28142", descricao: "COADOR DE PAPEL",
      exige_justificativa: true, justificativa: null, vinculo: null, alertas: [],
    },
    {
      empresa: empresa("1"), id_planilha: "8407024", dia: "2026-10-28", tipo: "entrada_avulsa", itens: 1,
      quantidade: "21", valor: "118.78", id_produto: "9657", id_subproduto: "9661", descricao: "TRINCO FIO CHATO",
      exige_justificativa: true, justificativa: null, vinculo: null,
      alertas: [
        {
          regra: "balanco", id_produto: "9657", id_subproduto: "9661", descricao: "TRINCO FIO CHATO", dia: "2026-10-26",
          id_planilha: "8389421", numero: null, operacao: "BALANCO", quantidade: "-21.0000", valor: "-118.78",
        },
        {
          regra: "uso_consumo", id_produto: "9657", id_subproduto: "9661", descricao: "TRINCO FIO CHATO", dia: "2026-10-20",
          id_planilha: "8380001", numero: "51234", operacao: "SAIDA PARA USO E CONSUMO", quantidade: "-21.0000", valor: "-118.78",
        },
      ],
    },
  ],
  pendentes: { documentos: 1, valor: "51.00" },
  pendentes_desde_o_corte: { documentos: 7, valor: "900.00" },
  justificadas: 3,
  motivos: [
    { codigo: "uso_consumo", rotulo: "Uso e consumo", tipos: ["saida_avulsa"], exige_observacao: false },
    { codigo: "mercadoria_encontrada", rotulo: "Mercadoria encontrada", tipos: ["entrada_avulsa"], exige_observacao: false },
    { codigo: "outro", rotulo: "Outro (descreva)", tipos: ["entrada_avulsa", "saida_avulsa"], exige_observacao: true },
  ],
  regras: [
    { codigo: "balanco", rotulo: "O último balanço tirou o produto", janela_dias: null },
    { codigo: "uso_consumo", rotulo: "Saiu para uso e consumo e voltou", janela_dias: 90 },
  ],
  corte: { justificar_desde: "2026-10-01", definido_por: null, atualizado_em: null },
};

const RECONTAGENS: Recontagens = {
  data_inicial: "2026-07-22",
  data_final: "2026-10-19",
  mais_de: 1,
  desde: null,
  total: 1,
  limite: 200,
  itens: [
    {
      empresa: empresa("1"), id_produto: "1194", id_subproduto: "1194", descricao: "THINNER 5L", marca: "TIGRE",
      contagens: 3, dias: ["2026-09-01", "2026-10-01", "2026-10-17"], quantidade: "-2", valor: "-80.00",
    },
  ],
  marcas: [
    { marca: "TIGRE", produtos: 1 },
    { marca: "3M", produtos: 4 },
    { marca: "TRAMONTINA", produtos: 2 },
  ],
};

const VER_9798 = "Ver estoque do produto 9798 por empresa";
const linhaCarregada = () => screen.findByRole("button", { name: VER_9798 });

const ultimaChamada = () => vi.mocked(getEstoque).mock.calls.at(-1)!;
const auth = () => authFalso(["ESTOQUE"]);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getResumoEstoque).mockResolvedValue(RESUMO);
  vi.mocked(getFornecedoresEstoque).mockResolvedValue([
    { cnpj: "11222333000181", nome: "FORNECEDOR FICTICIO LTDA", itens: 12 },
  ]);
  vi.mocked(getCoberturaEstoque).mockResolvedValue(COBERTURA);
  vi.mocked(getCoberturaLojas).mockResolvedValue(COBERTURA_LOJAS);
  vi.mocked(getExcecoesCobertura).mockResolvedValue([
    {
      empresa: empresa("1"),
      id_produto: "9798",
      id_subproduto: "9798",
      descricao: "CAFE FICTICIO 500G",
      motivo: "Só fica no depósito",
      usuario_nome: "Ana",
      criado_em: "2026-11-03T15:00:00Z",
    },
  ]);
  vi.mocked(incluirExcecaoCobertura).mockResolvedValue({ incluidos: 3 });
  vi.mocked(removerExcecaoCobertura).mockResolvedValue(undefined);
  vi.mocked(getPedidoAbastecimento).mockResolvedValue({
    loja: empresa("1"),
    janela: { inicio: "2026-10-05", fim: "2026-11-03", dias: 30 },
    alvo_dias: 30,
    tem_vendas: true,
    pedidos: [
      {
        deposito: empresa("4"),
        itens: [
          itemPedido({ id_produto: "5191", id_subproduto: "5191", marca: "3M", descricao: "ABAFADOR" }),
          itemPedido({ id_produto: "9528", id_subproduto: "9528", marca: "TIGRE", descricao: "CANO 25MM", quantidade: "12.000" }),
          itemPedido({ id_produto: "77", id_subproduto: "77", marca: null, descricao: "PREGO" }),
        ],
      },
      { deposito: empresa("5"), itens: [itemPedido({ id_produto: "9776", id_subproduto: "9776", marca: "REDEX" })] },
    ],
    sem_estoque: [itemPedido({ id_produto: "40", id_subproduto: "40", marca: "SUVINIL", quantidade: "0.000", disponivel_deposito: "0.000" })],
  });
  vi.mocked(getLivroEstoque).mockResolvedValue(LIVRO);
  vi.mocked(getNotasLivro).mockResolvedValue(NOTAS);
  vi.mocked(getItensNotaLivro).mockResolvedValue([
    { sequencia: "1", id_produto: "9798", id_subproduto: "9798", descricao: "CAFE FICTICIO 500G", quantidade: "-2.0000", valor: "-90.00" },
  ]);
  vi.mocked(getBalancos).mockResolvedValue(BALANCOS);
  vi.mocked(getRecontagens).mockResolvedValue(RECONTAGENS);
  vi.mocked(getDocumentosAvulsos).mockResolvedValue(DOCUMENTOS_AVULSOS);
  vi.mocked(justificarAvulsasEmLote).mockResolvedValue({ justificados: 2 });
  vi.mocked(justificarAvulsa).mockResolvedValue({
    motivo: "outro", motivo_rotulo: "Outro (descreva)", observacao: "teste", usuario_nome: "Ana", atualizado_em: "2026-10-28T15:00:00Z",
    pelo_vinculo: false,
  });
  vi.mocked(getCandidatosVinculo).mockResolvedValue([
    {
      id_planilha: "8390001", dia: "2026-10-27", tipo: "saida_avulsa", itens: 1, quantidade: "-21", valor: "-118.78",
      em_comum: 1, exato: true, id_produto: "9657", id_subproduto: "9661", descricao: "TRINCO FIO CHATO", justificativa: null,
    },
  ]);
  vi.mocked(relacionarAvulsas).mockResolvedValue({
    id_planilha: "8390001", dia: "2026-10-27", tipo: "saida_avulsa", usuario_nome: "Ana", criado_em: "2026-10-28T15:00:00Z",
  });
  vi.mocked(desfazerVinculo).mockResolvedValue(undefined);
  vi.mocked(getExtratoProduto).mockResolvedValue(EXTRATO);
  vi.mocked(getEstoque).mockResolvedValue(
    paginaDe([item(), item({ id_produto: "66", id_subproduto: "68", saldo_atual: "-4.500", saldo_disponivel: "-4.500" })]),
  );
  vi.mocked(getProdutoEstoque).mockResolvedValue(PRODUTO);
  vi.mocked(getMovimentosEstoque).mockResolvedValue(MOVIMENTOS);
});

const ultimaChamadaMovimentos = () => vi.mocked(getMovimentosEstoque).mock.calls.at(-1)!;

describe("EstoquePage", () => {
  it("mostra o resumo e o estoque consolidado", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });

    expect(screen.getByRole("heading", { level: 1, name: TITULO_ESTOQUE })).toBeInTheDocument();
    await linhaCarregada();
    expect(screen.getAllByText("188.525")).toHaveLength(2);


    expect(screen.getByText("68")).toBeInTheDocument();
    expect(screen.getByText(/grade 66/)).toBeInTheDocument();
    expect(screen.getAllByText("-4,5")).toHaveLength(2);
    expect(ultimaChamada()[0]).toEqual({ ordenacao: "produto" });
    expect(ultimaChamada()[1]).toBe(1);

    const resumo = screen.getByRole("region", { name: "Resumo do estoque" });
    await waitFor(() => expect(resumo).toHaveTextContent("20.664"));
    expect(resumo).toHaveTextContent("54");
    expect(screen.getByRole("heading", { name: "Estoque consolidado" })).toBeInTheDocument();
    expect(screen.getByRole("note", { name: "Locais de perda" })).toHaveTextContent(
      "LOCAL AVARIA da loja 6 · Avaria · R$ 1.111.111,00 em 1.234 produtos",
    );
  });

  it("filtra pelo fornecedor escolhido na lista, pelo CNPJ", async () => {
    const usuario = userEvent.setup();
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    const campo = screen.getByLabelText("Fornecedor");
    await waitFor(() =>
      expect(document.querySelector(`datalist[id="${campo.getAttribute("list")}"] option`)).not.toBeNull(),
    );


    await usuario.type(campo, "FORNEC");
    expect(ultimaChamada()[0].fornecedor).toBeUndefined();
    await usuario.tab();
    expect(campo).toHaveValue("");

    await usuario.click(campo);
    await usuario.paste("FORNECEDOR FICTICIO LTDA · 11.222.333/0001-81");
    await waitFor(() => expect(ultimaChamada()[0].fornecedor).toBe("11222333000181"));
    expect(ultimaChamada()[1]).toBe(1);

    await usuario.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(campo).toHaveValue("");
    await waitFor(() => expect(ultimaChamada()[0].fornecedor).toBeUndefined());
  });

  it("mostra descrição, faixa de preço, custo e valor do estoque", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    expect(screen.getAllByText("CAFE FICTICIO 500G").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MARCA FICTICIA").length).toBeGreaterThan(0);
    expect(screen.getAllByText("comprado de FORNECEDOR FICTICIO LTDA").length).toBeGreaterThan(0);

    expect(screen.getAllByText("R$ 12,90 – R$ 13,50").length).toBeGreaterThan(0);
    expect(screen.getAllByText("R$ 8,12").length).toBeGreaterThan(0);
    expect(screen.getAllByText("R$ 1.222.333,16").length).toBeGreaterThan(0);
    const resumo = screen.getByRole("region", { name: "Resumo do estoque" });
    await waitFor(() => expect(resumo).toHaveTextContent("R$ 2.500.000,56"));


    await userEvent.selectOptions(screen.getByLabelText("Empresa"), "2");
    await waitFor(() => expect(resumo).toHaveTextContent("R$ 700.000,46"));
  });

  it("filtra por empresa, situação e produto e volta para a página 1", async () => {
    vi.mocked(getEstoque).mockResolvedValue(paginaDe([item()], { total: 120, total_paginas: 3 }));
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    await userEvent.click(screen.getByRole("button", { name: "Próxima" }));
    await waitFor(() => expect(ultimaChamada()[1]).toBe(2));

    await userEvent.selectOptions(await screen.findByLabelText("Empresa"), "1");
    await waitFor(() => expect(ultimaChamada()[0]).toEqual({ ordenacao: "produto", empresa: "1" }));
    expect(ultimaChamada()[1]).toBe(1);
    expect(screen.getByRole("heading", { name: /Estoque · 1 - / })).toBeInTheDocument();

    expect(screen.queryByRole("columnheader", { name: "Empresas com saldo" })).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Situação"), "negativo");
    await userEvent.selectOptions(screen.getByLabelText("Ordenar por"), "maior_saldo");
    await userEvent.type(screen.getByLabelText("Código do produto"), "9798");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() =>
      expect(ultimaChamada()[0]).toEqual({
        ordenacao: "maior_saldo",
        empresa: "1",
        situacao: "negativo",
        produto: "9798",
      }),
    );

    await userEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    await waitFor(() => expect(ultimaChamada()[0]).toEqual({ ordenacao: "produto" }));
  });

  it("abre o detalhe do produto por empresa e local", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    await userEvent.click(screen.getByRole("button", { name: VER_9798 }));

    const dialogo = await screen.findByRole("dialog", { name: "Produto 9798" });
    expect(getProdutoEstoque).toHaveBeenCalledWith("9798", "9798", expect.any(AbortSignal), 30);
    const bloco = await within(dialogo).findByRole("region", { name: "Empresa 1" });
    expect(bloco).toHaveTextContent("DEPOSITO FUNDOS");
    expect(bloco).toHaveTextContent("R$ 12,90");
    expect(bloco).toHaveTextContent("R$ 121,85");

    expect(bloco).toHaveTextContent("Perda · Avaria (fora das somas)");
    expect(within(dialogo).getByText("CAFE FICTICIO 500G")).toBeInTheDocument();
    expect(within(dialogo).getAllByText("14").length).toBeGreaterThan(0);

    expect(dialogo).toHaveTextContent("Vende 2/dia na rede");
    expect(dialogo).toHaveTextContent("7 dias");
    expect(bloco).toHaveTextContent("Baixa");

    expect(dialogo).toHaveTextContent("Fabricante: MARCA FICTICIA");
    const fornecedores = within(dialogo).getByRole("region", { name: "Fornecedores" });
    expect(fornecedores).toHaveTextContent("FORNECEDOR FICTICIO LTDA");
    expect(fornecedores).toHaveTextContent("11.222.333/0001-81");
    expect(fornecedores).toHaveTextContent("02/10/2026");
    expect(fornecedores).toHaveTextContent("R$ 7,50");
  });

  it("detalhe traz o extrato da loja com saldo no fim do dia", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("button", { name: VER_9798 }));

    const extrato = await screen.findByRole("region", { name: "Extrato do produto" });
    await waitFor(() => expect(extrato).toHaveTextContent("Compra"));
    expect(vi.mocked(getExtratoProduto).mock.calls.at(-1)![2]).toMatchObject({ empresa: "1" });
    expect(extrato).toHaveTextContent("-5");
    expect(extrato).toHaveTextContent("20");
    expect(within(extrato).getByLabelText("Loja do extrato")).toHaveValue("1");
  });

  it("aba de entradas e saídas mostra o livro por loja e marca o que falta confirmar", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Entradas e saídas" }));

    const tabela = await screen.findByRole("table", { name: "Movimentos da loja 1 por operação" });
    expect(tabela).toHaveTextContent("COMPRA DE MERCADORIA");
    expect(tabela).toHaveTextContent("a confirmar · fora dos totais");

    const loja = tabela.closest("section")!;
    expect(loja).toHaveTextContent("Entradas R$ 1.500,00 · Saídas -R$ 900,50");
    expect(screen.getByRole("status")).toHaveTextContent("2 dia(s) × loja");
  });

  it("entradas e saídas filtram por categoria e mostram cada nota com hora, quem lançou e produtos", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Entradas e saídas" }));

    const notas = await screen.findByRole("table", { name: "Notas do livro de movimentação" });
    expect(notas).toHaveTextContent("ANTONIA");
    expect(notas).toHaveTextContent("19/10/2026, 13:50");
    expect(notas).toHaveTextContent("Nota 4521");
    expect(notas).toHaveTextContent("18/10/2026 · sem hora");

    await userEvent.click(within(notas).getByRole("button", { name: "Ver produtos do documento 8389517" }));
    const produtos = await screen.findByRole("table", { name: "Produtos do documento 8389517" });
    expect(produtos).toHaveTextContent("CAFE FICTICIO 500G");
    expect(getItensNotaLivro).toHaveBeenCalledWith("1", "8389517", expect.anything());

    await userEvent.selectOptions(screen.getByLabelText("Categoria"), "compra");
    await waitFor(() => expect(vi.mocked(getLivroEstoque).mock.calls.at(-1)![0]).toMatchObject({ categoria: "compra" }));
    expect(vi.mocked(getNotasLivro).mock.calls.at(-1)![0]).toMatchObject({ categoria: "compra" });

    await userEvent.click(await screen.findByRole("button", { name: "Ver notas do COI 11 da loja 1" }));
    await waitFor(() => expect(vi.mocked(getNotasLivro).mock.calls.at(-1)![0]).toMatchObject({ coi: 11, empresa: "1" }));
  });

  it("notas emitidas na empresa errada aparecem marcadas e têm filtro próprio", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Entradas e saídas" }));

    const notas = await screen.findByRole("table", { name: "Notas do livro de movimentação" });
    const errada = within(notas).getByText("Nota 213786").closest("tr")!;
    expect(errada).toHaveTextContent("Para: EMPRESA FICTICIA 5 (empresa 5)");
    expect(errada).toHaveTextContent("Empresa errada");
    const venda = within(notas).getByText("Nota 4521").closest("tr")!;
    expect(venda).toHaveTextContent("Para: CLIENTE FICTICIO");
    expect(venda).not.toHaveTextContent("Empresa errada");
    expect(vi.mocked(getNotasLivro).mock.calls.at(-1)![0]).not.toHaveProperty("empresa_errada");

    const filtro = screen.getByRole("button", { name: "Emitidas na empresa errada" });
    await userEvent.click(filtro);
    expect(filtro).toHaveAttribute("aria-pressed", "true");
    await waitFor(() =>
      expect(vi.mocked(getNotasLivro).mock.calls.at(-1)![0]).toMatchObject({ empresa_errada: true }),
    );
  });

  it("mostra venda por dia e cobertura de cada produto", async () => {
    vi.mocked(getEstoque).mockResolvedValue(
      paginaDe([
        item(),
        item({ id_produto: "66", id_subproduto: "66", saldo_disponivel: "0.000", cobertura_dias: "0.0", status_cobertura: "ruptura" }),
        item({ id_produto: "77", id_subproduto: "77", venda_media_diaria: null, cobertura_dias: null, status_cobertura: "sem_giro" }),
      ]),
    );
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    const tabela = screen.getByRole("table", { name: /Estoque por produto/ });
    expect(within(tabela).getByRole("columnheader", { name: "Venda/dia (30d)" })).toBeInTheDocument();
    expect(tabela).toHaveTextContent("1.250,5");
    expect(tabela).toHaveTextContent("150,8 dias");
    expect(tabela).toHaveTextContent("Excesso");
    expect(tabela).toHaveTextContent("0 dia");
    expect(tabela).toHaveTextContent("Ruptura");
    expect(tabela).toHaveTextContent("Sem giro");
  });

  it("faixas de cobertura contam e filtram a lista, dos que acabam primeiro", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    const faixas = await screen.findByRole("group", { name: "Filtrar por cobertura" });
    const ruptura = within(faixas).getByRole("button", { name: /Ruptura/ });
    await waitFor(() => expect(ruptura).toHaveTextContent("327"));
    expect(screen.getByText(/de 19\/09 a 18\/10/)).toBeInTheDocument();

    await userEvent.click(ruptura);
    expect(ruptura).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(ultimaChamada()[0]).toEqual({ ordenacao: "menor_cobertura", cobertura: "ruptura" }));


    await userEvent.click(ruptura);
    await waitFor(() => expect(ultimaChamada()[0]).toEqual({ ordenacao: "menor_cobertura" }));
  });

  it("troca a janela da média de vendas na lista e na contagem", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    await userEvent.selectOptions(screen.getByLabelText("Média de vendas"), "90");
    await waitFor(() => expect(ultimaChamada()[0]).toEqual({ ordenacao: "produto", janela_dias: 90 }));
    expect(vi.mocked(getCoberturaEstoque).mock.calls.at(-1)![0]).toEqual({ empresa: undefined, janela_dias: 90 });
  });

  it("empresa que não vende (depósito) fica sem cobertura", async () => {
    vi.mocked(getCoberturaEstoque).mockResolvedValue({ ...COBERTURA, tem_vendas: false });
    vi.mocked(getEstoque).mockResolvedValue(paginaDe([item({ status_cobertura: null })], { tem_vendas: false }));
    renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.selectOptions(await screen.findByLabelText("Empresa"), "2");

    expect(await screen.findByText(/não vendeu nada nos últimos 30 dias/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Filtrar por cobertura" })).not.toBeInTheDocument();
    await linhaCarregada();
    expect(screen.queryByRole("columnheader", { name: "Cobertura" })).not.toBeInTheDocument();
  });

  it("aba Loja conta a cobertura de cada empresa e local pela baixa do estoque e lista a faixa", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Loja" }));


    const lojas = await screen.findByRole("tablist", { name: "Lojas" });
    expect(within(lojas).getByRole("tab", { name: /^1 - .*1\.299 em ruptura/ })).toHaveAttribute("aria-selected", "true");
    const painel = screen.getByRole("tabpanel", { name: /^1 - / });

    expect(within(painel).getByRole("button", { name: "Ruptura em Empresa inteira: 1.299" })).toBeInTheDocument();

    expect(within(painel).getByRole("button", { name: "Ruptura em LOJA MATRIZ: 1.356" })).toBeInTheDocument();
    expect(within(painel).getByText("local 1 + DEPOSITO 03 e DEPOSITO 04")).toBeInTheDocument();
    expect(within(painel).getByRole("rowheader", { name: /^LOJA MATRIZ/ }).closest("tr")).toHaveTextContent("9.465");
    expect(within(painel).queryByRole("rowheader", { name: /^DEPOSITO 03/ })).not.toBeInTheDocument();
    expect(within(painel).getByRole("button", { name: "Crítica em MOSTRUARIO LOJA MATRIZ: 15" })).toBeInTheDocument();
    expect(screen.getByText(/o que a venda tirou do estoque da empresa por dia \(menos devoluções\)/)).toBeInTheDocument();

    expect(within(painel).queryByRole("rowheader", { name: /CENTRO/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Sem saldo positivo: LOJA CENTRO/)).toBeInTheDocument();
    expect(screen.getByText(/Desconsiderados \(não são de venda\): AVARIAS LOJA MATRIZ, PISO\./)).toBeInTheDocument();
    expect(screen.queryByText(/não vendeu nada nos últimos 30 dias/)).not.toBeInTheDocument();

    await userEvent.click(within(painel).getByRole("button", { name: "Ruptura em LOJA MATRIZ: 1.356" }));
    await waitFor(() =>
      expect(ultimaChamada()[0]).toEqual({
        empresa: "1",
        local: "1",
        cobertura: "ruptura",
        ordenacao: "menor_cobertura",
        media: "baixa",
        so_locais_da_loja: true,
        janela_dias: undefined,
      }),
    );
    expect(await screen.findByText(/Ruptura em LOJA MATRIZ/)).toBeInTheDocument();


    const chamadas = vi.mocked(getCoberturaLojas).mock.calls.length;
    await userEvent.click(await screen.findByRole("button", { name: /^Marcar 9798 como exceção de falta em 1 - / }));
    expect(vi.mocked(incluirExcecaoCobertura)).toHaveBeenCalledWith({ empresa: "1", codigo: "9798", motivo: null });
    expect(await screen.findByText(/O produto 9798 virou exceção em/)).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(getCoberturaLojas).mock.calls.length).toBeGreaterThan(chamadas));
    await userEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    expect(vi.mocked(removerExcecaoCobertura)).toHaveBeenCalledWith("1", "9798", "9798");
    expect(await screen.findByText(/O produto 9798 voltou a contar em/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Média de vendas"), "90");
    await waitFor(() => expect(vi.mocked(getCoberturaLojas).mock.calls.at(-1)![0]).toBe(90));
    await userEvent.click(within(lojas).getByRole("tab", { name: /^4 - .*depósito, sem venda/ }));
    expect(screen.queryByRole("button", { name: /em Empresa inteira/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Ruptura em LOJA MATRIZ/)).not.toBeInTheDocument();
    expect(screen.getByText(/não vendeu nada nos últimos \d+ dias \(depósito\)/)).toBeInTheDocument();
  });

  it("aba Loja monta o pedido de abastecimento por depósito e marca", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Loja" }));

    await userEvent.click(await screen.findByText("Pedido de abastecimento"));
    const depositos = await screen.findByRole("tablist", { name: "Pedido por depósito" });
    expect(vi.mocked(getPedidoAbastecimento).mock.calls.at(-1)!.slice(0, 3)).toEqual(["1", 30, undefined]);
    expect(within(depositos).getByRole("tab", { name: /^4 - .*3 itens · 3 marcas/ })).toHaveAttribute("aria-selected", "true");
    const painel = screen.getByRole("tabpanel", { name: /^4 - / });

    const grupos = within(painel).getAllByRole("columnheader").filter((c) => c.getAttribute("scope") === "colgroup");
    expect(grupos.map((g) => g.textContent)).toEqual(["3M · 1 item", "TIGRE · 1 item", "Sem marca · 1 item"]);
    expect(within(painel).getByRole("button", { name: "Exportar pedido" })).toBeInTheDocument();

    await userEvent.selectOptions(within(painel).getByLabelText("Marca"), "TIGRE");
    expect(within(painel).getByText("CANO 25MM")).toBeInTheDocument();
    expect(within(painel).queryByText("ABAFADOR")).not.toBeInTheDocument();


    expect(within(depositos).getAllByRole("tab")).toHaveLength(2);
    expect(screen.queryByText(/Sem estoque/)).not.toBeInTheDocument();
    await userEvent.click(within(depositos).getByRole("tab", { name: /^5 - / }));
    expect(screen.getByRole("tabpanel", { name: /^5 - / })).toHaveTextContent("REDEX");
    expect(screen.queryByText("SUVINIL")).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Cobrir"), "45");
    await waitFor(() => expect(vi.mocked(getPedidoAbastecimento).mock.calls.at(-1)![1]).toBe(45));
  });

  it("aba Loja inclui e tira exceções de falta da empresa e recarrega a contagem", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Loja" }));

    await userEvent.click(await screen.findByText(/Exceções de falta \(2\)/));
    const lista = await screen.findByRole("list", { name: "Exceções de falta · 1" });
    expect(within(lista).getByText("Só fica no depósito")).toBeInTheDocument();
    expect(vi.mocked(getExcecoesCobertura).mock.calls.at(-1)![0]).toBe("1");
    const chamadas = vi.mocked(getCoberturaLojas).mock.calls.length;
    const painel = within(lista.closest("details")!);

    await userEvent.type(painel.getByLabelText("Código do produto"), "50");
    await userEvent.type(painel.getByLabelText("Motivo (opcional)"), "Loja sem estrutura");
    await userEvent.click(painel.getByRole("button", { name: "Incluir" }));
    expect(vi.mocked(incluirExcecaoCobertura)).toHaveBeenCalledWith({
      empresa: "1",
      codigo: "50",
      motivo: "Loja sem estrutura",
    });
    expect(await screen.findByText("3 itens incluídos.")).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(getCoberturaLojas).mock.calls.length).toBeGreaterThan(chamadas));

    await userEvent.click(within(lista).getByRole("button", { name: "Tirar 9798 das exceções" }));
    expect(vi.mocked(removerExcecaoCobertura)).toHaveBeenCalledWith("1", "9798", "9798");

    vi.mocked(incluirExcecaoCobertura).mockRejectedValueOnce(new Error("Produto 999 não encontrado no cadastro."));
    await userEvent.type(painel.getByLabelText("Código do produto"), "999");
    await userEvent.click(painel.getByRole("button", { name: "Incluir" }));
    expect(await painel.findByRole("alert")).toHaveTextContent("Produto 999 não encontrado no cadastro.");
  });

  it("perfil de acesso: só as abas dele existem, e sem Justificativas o painel some", async () => {
    renderComSessao(<EstoquePage />, { auth: authFalso(["ESTOQUE"], undefined, ["ESTOQUE.AVULSAS"]) });

    const abas = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(abas).toEqual(["Avulsas"]);
    expect(screen.getByRole("tab", { name: "Avulsas" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(ultimaChamadaMovimentos()).toBeDefined());
    expect(screen.queryByText("Justificativas")).not.toBeInTheDocument();
  });

  it("aba de avulsas mostra só entradas e saídas avulsas, com resumo e itens", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));

    const hoje = hojeNoFuso();
    await waitFor(() =>

      expect(ultimaChamadaMovimentos()[0]).toEqual({
        data_inicial: hoje,
        data_final: hoje,
        tipo: "avulsas",
      }),
    );
    expect(await screen.findByRole("table", { name: /Resumo dos movimentos/ })).toHaveTextContent("Entrada avulsa");
    const itens = screen.getByRole("table", { name: "Movimentos de estoque" });
    expect(itens).toHaveTextContent("E1");

    expect(screen.queryByRole("list", { name: "Eventos de balanço" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Resumo do estoque" })).not.toBeInTheDocument();
  });

  it("aba de avulsas lista as pendentes e grava a justificativa do documento", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));

    const tabela = await screen.findByRole("table", { name: "Documentos avulsos e justificativas" });
    expect(tabela).toHaveTextContent("COADOR DE PAPEL");
    expect(tabela).toHaveTextContent("+ 1 item(ns)");
    expect(screen.getByText("7 pendentes")).toBeInTheDocument();
    expect(getDocumentosAvulsos).toHaveBeenLastCalledWith(
      expect.objectContaining({ situacao: "pendente" }), 1, 50, expect.any(AbortSignal),
    );

    await userEvent.click(within(tabela).getByRole("button", { name: "Justificar documento 8403635" }));
    const form = screen.getByRole("form", { name: "Justificativa do documento 8403635" });
    expect(getItensNotaLivro).toHaveBeenCalledWith("1", "8403635", expect.any(AbortSignal));

    const motivo = within(form).getByLabelText("Motivo");
    expect(within(motivo).queryByRole("option", { name: "Mercadoria encontrada" })).not.toBeInTheDocument();


    await userEvent.selectOptions(motivo, "outro");
    await userEvent.click(within(form).getByRole("button", { name: "Gravar justificativa" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Descreva o motivo");
    expect(justificarAvulsa).not.toHaveBeenCalled();

    await userEvent.type(within(form).getByLabelText(/Observação/), "  teste  ");
    const chamadas = vi.mocked(getDocumentosAvulsos).mock.calls.length;
    await userEvent.click(within(form).getByRole("button", { name: "Gravar justificativa" }));
    expect(justificarAvulsa).toHaveBeenCalledWith(
      expect.objectContaining({ id_planilha: "8403635" }),
      { motivo: "outro", observacao: "teste" },
    );

    await waitFor(() => expect(vi.mocked(getDocumentosAvulsos).mock.calls.length).toBeGreaterThan(chamadas));
    expect(screen.queryByRole("form", { name: "Justificativa do documento 8403635" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: /Justificadas/ }));
    await waitFor(() =>
      expect(getDocumentosAvulsos).toHaveBeenLastCalledWith(
        expect.objectContaining({ situacao: "justificada" }), 1, 50, expect.any(AbortSignal),
      ),
    );
  });

  it("entrada avisa o balanço que tirou o produto e relaciona com a saída sugerida", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));
    const tabela = await screen.findByRole("table", { name: "Documentos avulsos e justificativas" });

    expect(tabela).toHaveTextContent("O último balanço tirou o produto (26/10/2026, doc. 8389421): 21 un.");
    expect(tabela).toHaveTextContent("e mais 1 aviso(s)");

    await userEvent.click(within(tabela).getByRole("button", { name: "Justificar documento 8407024" }));
    expect(getCandidatosVinculo).toHaveBeenCalledWith(
      expect.objectContaining({ id_planilha: "8407024" }),
      expect.any(AbortSignal),
    );
    const sugestoes = await screen.findByRole("list", { name: "Saídas que podem ser o par" });
    expect(sugestoes).toHaveTextContent("Mesmos itens");
    const chamadas = vi.mocked(getDocumentosAvulsos).mock.calls.length;
    await userEvent.click(within(sugestoes).getByRole("button", { name: "Relacionar com saída 8390001" }));
    expect(relacionarAvulsas).toHaveBeenCalledWith(expect.objectContaining({ id_planilha: "8407024" }), "8390001");
    await waitFor(() => expect(vi.mocked(getDocumentosAvulsos).mock.calls.length).toBeGreaterThan(chamadas));
  });

  it("seleciona vários documentos e justifica todos juntos", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));
    const tabela = await screen.findByRole("table", { name: "Documentos avulsos e justificativas" });

    await userEvent.click(within(tabela).getByRole("checkbox", { name: "Selecionar todos da página" }));
    const barra = screen.getByRole("region", { name: "Documentos selecionados" });
    expect(barra).toHaveTextContent("2 documentos selecionados");
    await userEvent.click(within(barra).getByRole("button", { name: "Justificar os 2 juntos" }));

    const form = within(barra).getByRole("form", { name: "Justificativa dos 2 documentos selecionados" });

    const motivo = within(form).getByLabelText("Motivo");
    expect(within(motivo).queryByRole("option", { name: "Uso e consumo" })).not.toBeInTheDocument();
    expect(within(motivo).queryByRole("option", { name: "Mercadoria encontrada" })).not.toBeInTheDocument();
    await userEvent.selectOptions(motivo, "outro");
    await userEvent.type(within(form).getByLabelText(/Observação/), "acerto do mês");
    const chamadas = vi.mocked(getDocumentosAvulsos).mock.calls.length;
    await userEvent.click(within(form).getByRole("button", { name: "Gravar nos 2" }));

    expect(justificarAvulsasEmLote).toHaveBeenCalledWith(
      [expect.objectContaining({ id_planilha: "8403635" }), expect.objectContaining({ id_planilha: "8407024" })],
      { motivo: "outro", observacao: "acerto do mês" },
    );
    await waitFor(() => expect(vi.mocked(getDocumentosAvulsos).mock.calls.length).toBeGreaterThan(chamadas));
    expect(screen.queryByRole("region", { name: "Documentos selecionados" })).not.toBeInTheDocument();
  });

  it("filtra as entradas que voltaram depois de sair para uso e consumo", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));
    const tabela = await screen.findByRole("table", { name: "Documentos avulsos e justificativas" });

    await userEvent.selectOptions(screen.getByLabelText("Avisos"), "uso_consumo");
    await waitFor(() =>
      expect(getDocumentosAvulsos).toHaveBeenLastCalledWith(
        expect.objectContaining({ alerta: "uso_consumo" }), 1, 50, expect.any(AbortSignal),
      ),
    );
    await userEvent.click(within(tabela).getByRole("button", { name: "Justificar documento 8407024" }));

    expect(screen.getAllByRole("list", { name: "Avisos da entrada" }).at(-1)).toHaveTextContent(
      "Saiu para uso e consumo e voltou (20/10/2026, nota 51234): 21 un.",
    );
  });

  it("só o ADMIN altera o dia de corte das justificativas", async () => {
    vi.mocked(definirCorteAvulsas).mockResolvedValue({
      justificar_desde: null, definido_por: "Ana", atualizado_em: "2026-10-29T15:00:00Z",
    });
    const { unmount } = renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));
    expect(await screen.findByText("01/10/2026")).toBeInTheDocument();
    expect(screen.getByText("· padrão do servidor")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Alterar" })).not.toBeInTheDocument();
    unmount();

    renderComSessao(<EstoquePage />, { auth: authFalso(["ESTOQUE"], usuarioTeste({ role: "ADMIN" })) });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));
    await userEvent.click(await screen.findByRole("button", { name: "Alterar" }));
    const form = screen.getByRole("form", { name: "Dia de corte das justificativas" });
    const campo = within(form).getByLabelText("Cobrar as avulsas a partir de");
    expect(campo).toHaveValue("2026-10-01");

    await userEvent.clear(campo);
    const chamadas = vi.mocked(getDocumentosAvulsos).mock.calls.length;
    await userEvent.click(within(form).getByRole("button", { name: "Gravar dia de corte" }));
    expect(definirCorteAvulsas).toHaveBeenCalledWith(null);
    await waitFor(() => expect(vi.mocked(getDocumentosAvulsos).mock.calls.length).toBeGreaterThan(chamadas));
  });

  it("documento relacionado mostra o par e desfaz o vínculo", async () => {
    const [saida, entrada] = DOCUMENTOS_AVULSOS.documentos;
    vi.mocked(getDocumentosAvulsos).mockResolvedValue({
      ...DOCUMENTOS_AVULSOS,
      documentos: [
        saida!,
        {
          ...entrada!,
          vinculo: { id_planilha: "8390001", dia: "2026-10-27", tipo: "saida_avulsa", usuario_nome: "Ana", criado_em: "2026-10-28T15:00:00Z" },
          justificativa: {
            motivo: "correcao_lancamento", motivo_rotulo: "Correção de lançamento", pelo_vinculo: true,
            observacao: "Relacionada com a saída avulsa 8390001 de 27/10/2026.", usuario_nome: "Ana", atualizado_em: "2026-10-28T15:00:00Z",
          },
        },
      ],
    });
    renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));
    const tabela = await screen.findByRole("table", { name: "Documentos avulsos e justificativas" });
    expect(tabela).toHaveTextContent("Saída 8390001");

    await userEvent.click(within(tabela).getByRole("button", { name: "Editar justificativa do documento 8407024" }));
    expect(getCandidatosVinculo).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Desfazer vínculo" }));
    expect(desfazerVinculo).toHaveBeenCalledWith(expect.objectContaining({ id_planilha: "8407024" }));
  });

  it("filtra as avulsas por tipo e produto", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await userEvent.click(screen.getByRole("tab", { name: "Avulsas" }));
    await screen.findByRole("table", { name: "Movimentos de estoque" });

    await userEvent.selectOptions(screen.getByLabelText("Tipo"), "saida_avulsa");
    await waitFor(() => expect(ultimaChamadaMovimentos()[0]).toMatchObject({ tipo: "saida_avulsa" }));
    expect(within(screen.getByLabelText("Tipo")).queryByRole("option", { name: "Balanço" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Produto"), "9798");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(ultimaChamadaMovimentos()[0]).toMatchObject({ produto: "9798" }));
  });

  it("aba de balanço mostra perda, ganho, transferências prováveis e os itens de cada balanço", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Balanço" }));

    const resultado = await screen.findByRole("region", { name: "Resultado dos balanços" });
    expect(resultado).toHaveTextContent("-R$ 1.000,00");
    expect(resultado).toHaveTextContent("R$ 400,00");
    expect(resultado).toHaveTextContent("-R$ 600,00");
    expect(resultado).toHaveTextContent("25% da perda");
    expect(resultado).toHaveTextContent("Perda · Avaria");
    expect(resultado).toHaveTextContent("R$ 1.111.111,00");
    expect(screen.getByRole("table", { name: "Prováveis transferências erradas" })).toHaveTextContent("THINNER");
    expect(screen.getByRole("table", { name: "Maiores perdas" })).toHaveTextContent("SELANTE");

    const evento = screen.getByRole("listitem", { name: "Balanço 17/10/2026 loja 1" });
    await userEvent.click(within(evento).getByRole("button", { name: "Ver itens" }));
    await waitFor(() =>
      expect(ultimaChamadaMovimentos()[0]).toEqual({
        data_inicial: "2026-10-17",
        data_final: "2026-10-17",
        empresa: "1",
        tipo: "balanco",
      }),
    );

    const detalhe = await screen.findByRole("listitem", { name: "Itens do balanço 17/10/2026 loja 1" });
    expect(evento.nextElementSibling).toBe(detalhe);
    expect(await within(detalhe).findByRole("table", { name: "Movimentos de estoque" })).toBeInTheDocument();
    const fechar = within(evento).getByRole("button", { name: "Fechar itens" });
    expect(fechar).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(fechar);
    expect(screen.queryByRole("listitem", { name: "Itens do balanço 17/10/2026 loja 1" })).not.toBeInTheDocument();
  });

  it("aba de balanço alerta os itens recontados e filtra por vezes e data", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Balanço" }));

    expect(await screen.findByText(/1 produto contado mais de 1 vez/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Itens recontados nos balanços" })).toHaveTextContent("THINNER");
    expect(getRecontagens).toHaveBeenLastCalledWith(expect.objectContaining({ mais_de: 1 }), expect.any(AbortSignal));

    const vezes = screen.getByLabelText("Contado mais de (vezes)");
    await userEvent.clear(vezes);
    await userEvent.type(vezes, "3");
    fireEvent.change(screen.getByLabelText("Recontado a partir de"), { target: { value: "2026-10-10" } });
    await waitFor(() =>
      expect(getRecontagens).toHaveBeenLastCalledWith(
        expect.objectContaining({ mais_de: 3, desde: "2026-10-10" }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("itens recontados filtram por mais de uma marca", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();
    await userEvent.click(screen.getByRole("tab", { name: "Balanço" }));
    await screen.findByText(/1 produto contado mais de 1 vez/);

    await userEvent.click(screen.getByRole("button", { name: "Marcas: Todas" }));
    const lista = screen.getByRole("list", { name: "Marcas dos recontados" });
    await userEvent.click(within(lista).getByRole("checkbox", { name: /TIGRE/ }));
    await userEvent.type(screen.getByLabelText("Buscar marca"), "tra");
    expect(within(lista).queryByRole("checkbox", { name: /3M/ })).not.toBeInTheDocument();
    await userEvent.click(within(lista).getByRole("checkbox", { name: /TRAMONTINA/ }));
    await waitFor(() =>
      expect(getRecontagens).toHaveBeenLastCalledWith(
        expect.objectContaining({ marca: ["TIGRE", "TRAMONTINA"] }),
        expect.any(AbortSignal),
      ),
    );
    expect(screen.getByRole("button", { name: "Marcas: 2 marcas" })).toBeInTheDocument();


    const escolhidas = screen.getByRole("list", { name: "Marcas escolhidas" });
    await userEvent.click(within(escolhidas).getByRole("button", { name: "Tirar a marca TIGRE" }));
    await waitFor(() =>
      expect(getRecontagens).toHaveBeenLastCalledWith(
        expect.objectContaining({ marca: ["TRAMONTINA"] }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("detalhe do produto mostra os últimos movimentos dele", async () => {
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    await userEvent.click(screen.getByRole("button", { name: VER_9798 }));

    const dialogo = await screen.findByRole("dialog", { name: "Produto 9798" });
    const secao = await within(dialogo).findByRole("region", { name: "Últimos movimentos" });
    expect(getMovimentosEstoque).toHaveBeenCalledWith({ produto: "9798", subproduto: "9798" }, 1, 10, expect.any(AbortSignal));
    expect(await within(secao).findByText("E1")).toBeInTheDocument();
    expect(within(secao).getByText("Balanço")).toBeInTheDocument();
  });

  it("produto sem estoque no detalhe mostra aviso", async () => {
    vi.mocked(getProdutoEstoque).mockRejectedValue(new ApiError("Produto sem estoque.", "http", 404));
    renderComSessao(<EstoquePage />, { auth: auth() });
    await linhaCarregada();

    await userEvent.click(screen.getByRole("button", { name: VER_9798 }));

    expect(await screen.findByText("Produto sem estoque registrado")).toBeInTheDocument();
  });

  it("lista vazia sem filtros explica que ainda não houve sincronização", async () => {
    vi.mocked(getEstoque).mockResolvedValue(paginaDe([]));
    renderComSessao(<EstoquePage />, { auth: auth() });

    expect(await screen.findByText("Nenhum estoque sincronizado ainda.")).toBeInTheDocument();
  });

  it("falha na lista mostra erro com nova tentativa", async () => {
    vi.mocked(getEstoque).mockRejectedValue(new Error("rede fora"));
    renderComSessao(<EstoquePage />, { auth: auth() });

    expect(await screen.findByText("Falha ao carregar o estoque")).toBeInTheDocument();
    vi.mocked(getEstoque).mockResolvedValue(paginaDe([item()]));
    await userEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    expect(await linhaCarregada()).toBeInTheDocument();
  });
});
