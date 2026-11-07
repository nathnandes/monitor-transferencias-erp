

import type { ConfiguracaoMetas, MetaEntrada, ProgressoMetas, VendedorOpcao } from "../types/api";
import { deleteJson, getJson, putJson } from "./apiClient";

export const CAMINHO_METAS = "/api/v1/vendas/metas";

export function getMetas(signal?: AbortSignal): Promise<ConfiguracaoMetas> {
  return getJson<ConfiguracaoMetas>(CAMINHO_METAS, { signal });
}


export function getProgressoMetas(dia: string, signal?: AbortSignal): Promise<ProgressoMetas> {
  return getJson<ProgressoMetas>(`${CAMINHO_METAS}/progresso`, { params: { dia: dia || undefined }, signal });
}

export function getVendedoresMeta(signal?: AbortSignal): Promise<VendedorOpcao[]> {
  return getJson<VendedorOpcao[]>(`${CAMINHO_METAS}/vendedores`, { signal });
}


export function salvarMeta(dados: MetaEntrada): Promise<ConfiguracaoMetas> {
  return putJson<ConfiguracaoMetas>(CAMINHO_METAS, dados);
}

export function excluirMeta(id: number): Promise<void> {
  return deleteJson(`${CAMINHO_METAS}/${id}`);
}

export function salvarMarcos(marcos: number[]): Promise<ConfiguracaoMetas> {
  return putJson<ConfiguracaoMetas>(`${CAMINHO_METAS}/marcos`, { marcos });
}
