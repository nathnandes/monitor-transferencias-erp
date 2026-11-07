

import type { ParamsExportarDescontos, ParamsVendas, ResumoVendas } from "../types/api";
import { ApiError, baixarArquivo, getJson } from "./apiClient";
import { ehObjeto } from "./validacao";

export const CAMINHO_RESUMO_VENDAS = "/api/v1/vendas/resumo";

export const CAMINHO_EXPORTAR_FORMAS = "/api/v1/vendas/formas-pagamento/exportar";

export const CAMINHO_EXPORTAR_DESCONTOS = "/api/v1/vendas/descontos/exportar";

function totaisValidos(t: unknown): boolean {
  return ehObjeto(t) && typeof t.faturamento === "string" && Number.isInteger(t.notas) && typeof t.quantidade === "string";
}

export function validarResumoVendas(dados: unknown): ResumoVendas {
  const problemas: string[] = [];
  if (!ehObjeto(dados)) {
    problemas.push("corpo não é um objeto");
  } else {
    if (typeof dados.gerado_em !== "string") problemas.push("gerado_em");
    if (!totaisValidos(dados.totais)) problemas.push("totais");
    if (dados.comparacao !== null && !totaisValidos(dados.comparacao)) problemas.push("comparacao");
    if (dados.granularidade !== "dia" && dados.granularidade !== "mes") problemas.push("granularidade");
    for (const lista of ["serie", "por_canal", "por_categoria", "por_empresa", "produtos"])
      if (!Array.isArray(dados[lista])) problemas.push(lista);
    if (!ehObjeto(dados.filtro)) problemas.push("filtro");
    if (!ehObjeto(dados.cobertura)) problemas.push("cobertura");
    if (!ehObjeto(dados.vendedores) || !Array.isArray(dados.vendedores.vendedores)) problemas.push("vendedores");
  }
  if (problemas.length) {
    throw new ApiError(
      `O resumo de vendas veio em formato inesperado (${problemas.join(", ")}). Verifique se frontend e backend estão na mesma versão.`,
      "resposta_invalida",
    );
  }
  return dados as unknown as ResumoVendas;
}


export async function getResumoVendas(params: ParamsVendas = {}, signal?: AbortSignal): Promise<ResumoVendas> {
  const preenchidos = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
  const dados = await getJson<unknown>(CAMINHO_RESUMO_VENDAS, { params: preenchidos, signal });
  return validarResumoVendas(dados);
}


export async function exportarFormasPagamento(params: ParamsVendas = {}): Promise<void> {
  const preenchidos = Object.fromEntries(Object.entries(params).filter(([chave, v]) => v && chave !== "canal"));
  await baixarArquivo(CAMINHO_EXPORTAR_FORMAS, preenchidos, "vendas_formas_pagamento.xlsx");
}


export async function exportarDescontos(params: ParamsExportarDescontos): Promise<void> {
  const preenchidos = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
  await baixarArquivo(CAMINHO_EXPORTAR_DESCONTOS, preenchidos, "vendas_descontos.xlsx");
}
