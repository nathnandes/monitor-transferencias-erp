

import type {
  CoberturaLojas,
  ExcecaoCobertura,
  NovaExcecaoCobertura,
  PedidoAbastecimento,
  ResultadoExcecaoCobertura,
  ExtratoProduto,
  FornecedorEstoque,
  CandidatoVinculo,
  CorteAvulsas,
  DocumentoAvulso,
  ItemNotaLivro,
  JustificativaAvulsa,
  LivroEstoque,
  NovaJustificativaAvulsa,
  PaginaDocumentosAvulsos,
  PaginaEstoque,
  PaginaMovimentosEstoque,
  PaginaNotasLivro,
  ParamsDocumentosAvulsos,
  ParamsEstoque,
  ParamsLivro,
  ParamsMovimentos,
  ParamsNotasLivro,
  ParamsRecontagens,
  ProdutoEstoque,
  Recontagens,
  ResumoBalancos,
  ResumoCobertura,
  ResumoEstoque,
  ResultadoLoteJustificativas,
  VinculoAvulsa,
} from "../types/api";
import { deleteJson, getJson, postJson, putJson } from "./apiClient";
import { booleano, inteiro, lista, objeto, ouNulo, PAGINACAO, texto, validarFormato } from "./validacao";


export const TAMANHO_PAGINA_MAXIMO = 100;

export function getEstoque(
  filtros: ParamsEstoque,
  pagina = 1,
  tamanhoPagina = 50,
  signal?: AbortSignal,
): Promise<PaginaEstoque> {
  const tamanho = Math.min(Math.max(1, Math.trunc(tamanhoPagina)), TAMANHO_PAGINA_MAXIMO);
  return getJson<unknown>("/api/v1/estoque", {
    params: {
      ...filtros,
      produto: filtros.produto?.trim(),
      pagina: Math.max(1, Math.trunc(pagina)),
      tamanho_pagina: tamanho,
    },
    signal,
  }).then((dados) =>
    validarFormato<PaginaEstoque>(dados, "A lista de estoque", {
      ...PAGINACAO,
      atualizado_em: ouNulo(texto),
      janela: objeto,
      tem_vendas: booleano,
    }),
  );
}

export function getResumoEstoque(signal?: AbortSignal): Promise<ResumoEstoque> {
  return getJson<ResumoEstoque>("/api/v1/estoque/resumo", { signal });
}


export function getCoberturaEstoque(
  params: Pick<ParamsEstoque, "empresa" | "local" | "janela_dias">,
  signal?: AbortSignal,
): Promise<ResumoCobertura> {
  return getJson<ResumoCobertura>("/api/v1/estoque/cobertura", { params: { ...params }, signal });
}


export function getFornecedoresEstoque(signal?: AbortSignal): Promise<FornecedorEstoque[]> {
  return getJson<FornecedorEstoque[]>("/api/v1/estoque/fornecedores", { signal });
}


export function getCoberturaLojas(janelaDias?: number, signal?: AbortSignal): Promise<CoberturaLojas> {
  return getJson<CoberturaLojas>("/api/v1/estoque/cobertura/lojas", { params: { janela_dias: janelaDias }, signal });
}


export function getPedidoAbastecimento(
  loja: string,
  alvoDias: number,
  janelaDias?: number,
  signal?: AbortSignal,
): Promise<PedidoAbastecimento> {
  return getJson<PedidoAbastecimento>("/api/v1/estoque/pedido-abastecimento", {
    params: { loja, alvo_dias: alvoDias, janela_dias: janelaDias },
    signal,
  });
}


export function getExcecoesCobertura(empresa?: string, signal?: AbortSignal): Promise<ExcecaoCobertura[]> {
  return getJson<ExcecaoCobertura[]>("/api/v1/estoque/excecoes", { params: { empresa }, signal });
}


export function incluirExcecaoCobertura(dados: NovaExcecaoCobertura): Promise<ResultadoExcecaoCobertura> {
  return postJson<ResultadoExcecaoCobertura>("/api/v1/estoque/excecoes", dados);
}

export function removerExcecaoCobertura(empresa: string, idProduto: string, idSubproduto: string): Promise<void> {
  const caminho = [empresa, idProduto, idSubproduto].map(encodeURIComponent).join("/");
  return deleteJson(`/api/v1/estoque/excecoes/${caminho}`);
}

export function getProdutoEstoque(
  idProduto: string,
  idSubproduto: string,
  signal?: AbortSignal,
  janelaDias?: number,
): Promise<ProdutoEstoque> {
  const caminho = `/api/v1/estoque/${encodeURIComponent(idProduto)}/${encodeURIComponent(idSubproduto)}`;
  return getJson<ProdutoEstoque>(caminho, { params: { janela_dias: janelaDias }, signal });
}


export function getMovimentosEstoque(
  filtros: ParamsMovimentos,
  pagina = 1,
  tamanhoPagina = 50,
  signal?: AbortSignal,
): Promise<PaginaMovimentosEstoque> {
  const tamanho = Math.min(Math.max(1, Math.trunc(tamanhoPagina)), TAMANHO_PAGINA_MAXIMO);
  return getJson<PaginaMovimentosEstoque>("/api/v1/estoque/movimentos", {
    params: {
      ...filtros,
      produto: filtros.produto?.trim() || undefined,
      pagina: Math.max(1, Math.trunc(pagina)),
      tamanho_pagina: tamanho,
    },
    signal,
  });
}


export function getLivroEstoque(params: ParamsLivro, signal?: AbortSignal): Promise<LivroEstoque> {
  return getJson<unknown>("/api/v1/estoque/livro", { params: { ...params }, signal }).then((dados) =>
    validarFormato<LivroEstoque>(dados, "O livro de movimentação", {
      data_inicial: texto,
      data_final: texto,
      linhas: lista,
      dias_sem_leitura: inteiro,
    }),
  );
}


export function getNotasLivro(
  params: ParamsNotasLivro,
  pagina: number,
  tamanho: number,
  signal?: AbortSignal,
): Promise<PaginaNotasLivro> {
  return getJson<PaginaNotasLivro>("/api/v1/estoque/livro/notas", {
    params: { ...params, pagina: Math.max(1, Math.trunc(pagina)), tamanho_pagina: tamanho },
    signal,
  });
}


export function getItensNotaLivro(empresa: string, idPlanilha: string, signal?: AbortSignal): Promise<ItemNotaLivro[]> {
  const caminho = `/api/v1/estoque/livro/notas/${encodeURIComponent(empresa)}/${encodeURIComponent(idPlanilha)}`;
  return getJson<ItemNotaLivro[]>(caminho, { signal });
}


export function getExtratoProduto(
  idProduto: string,
  idSubproduto: string,
  params: ParamsLivro & { empresa: string },
  signal?: AbortSignal,
): Promise<ExtratoProduto> {
  const caminho = `/api/v1/estoque/${encodeURIComponent(idProduto)}/${encodeURIComponent(idSubproduto)}/extrato`;
  return getJson<ExtratoProduto>(caminho, { params: { ...params }, signal });
}


export function getBalancos(params: ParamsLivro, signal?: AbortSignal): Promise<ResumoBalancos> {
  return getJson<ResumoBalancos>("/api/v1/estoque/balancos", { params: { ...params }, signal });
}

export function getRecontagens(params: ParamsRecontagens, signal?: AbortSignal): Promise<Recontagens> {
  return getJson<Recontagens>("/api/v1/estoque/balancos/recontagens", { params: { ...params }, signal });
}


export function getDocumentosAvulsos(
  params: ParamsDocumentosAvulsos,
  pagina: number,
  tamanhoPagina: number,
  signal?: AbortSignal,
): Promise<PaginaDocumentosAvulsos> {
  return getJson<PaginaDocumentosAvulsos>("/api/v1/estoque/avulsas/documentos", {
    params: { ...params, pagina, tamanho_pagina: tamanhoPagina },
    signal,
  });
}


export function justificarAvulsa(
  documento: Pick<DocumentoAvulso, "empresa" | "id_planilha">,
  dados: NovaJustificativaAvulsa,
): Promise<JustificativaAvulsa> {
  return putJson<JustificativaAvulsa>(`${caminhoAvulsa(documento)}/justificativa`, dados);
}

type RefDocumento = Pick<DocumentoAvulso, "empresa" | "id_planilha">;


export function definirCorteAvulsas(justificarDesde: string | null): Promise<CorteAvulsas> {
  return putJson<CorteAvulsas>("/api/v1/estoque/avulsas/corte", { justificar_desde: justificarDesde });
}


export function justificarAvulsasEmLote(
  documentos: RefDocumento[],
  dados: NovaJustificativaAvulsa,
): Promise<ResultadoLoteJustificativas> {
  return putJson<ResultadoLoteJustificativas>("/api/v1/estoque/avulsas/justificativas", {
    ...dados,
    documentos: documentos.map((d) => ({ empresa: d.empresa.codigo, id_planilha: d.id_planilha })),
  });
}

const caminhoAvulsa = (d: RefDocumento) =>
  `/api/v1/estoque/avulsas/${encodeURIComponent(d.empresa.codigo)}/${encodeURIComponent(d.id_planilha)}`;


export function getCandidatosVinculo(documento: RefDocumento, signal?: AbortSignal): Promise<CandidatoVinculo[]> {
  return getJson<CandidatoVinculo[]>(`${caminhoAvulsa(documento)}/candidatos`, { signal });
}


export function relacionarAvulsas(documento: RefDocumento, outroIdPlanilha: string): Promise<VinculoAvulsa> {
  return putJson<VinculoAvulsa>(`${caminhoAvulsa(documento)}/vinculo`, { id_planilha: outroIdPlanilha });
}


export function desfazerVinculo(documento: RefDocumento): Promise<void> {
  return deleteJson(`${caminhoAvulsa(documento)}/vinculo`);
}
