

import type {
  PaginaParcelas,
  ParamsFinanceiro,
  ParamsParcelas,
  ResumoFinanceiro,
} from "../types/api";
import { ApiError, getJson } from "./apiClient";
import { ehObjeto } from "./validacao";

export const CAMINHO_RESUMO_FINANCEIRO = "/api/v1/financeiro/resumo";
export const CAMINHO_PARCELAS = "/api/v1/financeiro/parcelas";

export function validarResumoFinanceiro(dados: unknown): ResumoFinanceiro {
  const problemas: string[] = [];
  if (!ehObjeto(dados)) {
    problemas.push("corpo não é um objeto");
  } else {
    if (typeof dados.gerado_em !== "string") problemas.push("gerado_em");
    if (!ehObjeto(dados.filtro)) problemas.push("filtro");
    if (!ehObjeto(dados.cobertura)) problemas.push("cobertura");
    const { vendas, recebidos } = dados;
    if (
      !ehObjeto(vendas) ||
      typeof vendas.valor !== "string" ||
      !Array.isArray(vendas.formas)
    )
      problemas.push("vendas");
    if (
      !ehObjeto(recebidos) ||
      typeof recebidos.total !== "string" ||
      !Array.isArray(recebidos.formas)
    )
      problemas.push("recebidos");
  }
  if (problemas.length) {
    throw new ApiError(
      `O resumo financeiro veio em formato inesperado (${problemas.join(", ")}). Verifique se frontend e backend estão na mesma versão.`,
      "resposta_invalida",
    );
  }
  return dados as unknown as ResumoFinanceiro;
}


export async function getResumoFinanceiro(
  params: ParamsFinanceiro = {},
  signal?: AbortSignal,
): Promise<ResumoFinanceiro> {
  const preenchidos = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v),
  );
  const dados = await getJson<unknown>(CAMINHO_RESUMO_FINANCEIRO, {
    params: preenchidos,
    signal,
  });
  return validarResumoFinanceiro(dados);
}

export function validarPaginaParcelas(dados: unknown): PaginaParcelas {
  if (
    !ehObjeto(dados) ||
    typeof dados.total !== "number" ||
    typeof dados.valor !== "string" ||
    !Array.isArray(dados.itens)
  ) {
    throw new ApiError(
      "A lista de parcelas veio em formato inesperado. Verifique se frontend e backend estão na mesma versão.",
      "resposta_invalida",
    );
  }
  return dados as unknown as PaginaParcelas;
}


export async function getParcelas(
  params: ParamsParcelas = {},
  signal?: AbortSignal,
): Promise<PaginaParcelas> {
  const preenchidos = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== ""),
  );
  const dados = await getJson<unknown>(CAMINHO_PARCELAS, {
    params: preenchidos,
    signal,
  });
  return validarPaginaParcelas(dados);
}
