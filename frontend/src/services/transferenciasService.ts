

import type {
  PaginaTransferencias,
  ParamsTransferencias,
  Transferencia,
  TransferenciaDetalhe,
} from "../types/api";
import { getJson } from "./apiClient";
import { PAGINACAO, validarFormato } from "./validacao";


export const TAMANHO_PAGINA_MAXIMO = 100;

export function getTransferencias(
  filtros: ParamsTransferencias,
  pagina = 1,
  tamanhoPagina = 20,
  signal?: AbortSignal,
): Promise<PaginaTransferencias> {

  const tamanho = Math.min(Math.max(1, Math.trunc(tamanhoPagina)), TAMANHO_PAGINA_MAXIMO);
  return getJson<unknown>("/api/v1/transferencias", {
    params: { ...filtros, pagina: Math.max(1, Math.trunc(pagina)), tamanho_pagina: tamanho },
    signal,
  }).then((dados) => validarFormato<PaginaTransferencias>(dados, "A lista de transferências", PAGINACAO));
}

export function getTransferencia(id: number, signal?: AbortSignal): Promise<TransferenciaDetalhe> {
  return getJson<TransferenciaDetalhe>(`/api/v1/transferencias/${id}`, { signal });
}

export interface ColetaTransferencias {
  itens: Transferencia[];

  total: number;

  truncado: boolean;
}


export async function coletarTransferencias(
  filtros: ParamsTransferencias,
  maxPaginas = 10,
  signal?: AbortSignal,
): Promise<ColetaTransferencias> {
  const primeira = await getTransferencias(filtros, 1, TAMANHO_PAGINA_MAXIMO, signal);
  const itens = [...primeira.itens];
  const ultimaPagina = Math.min(primeira.total_paginas, maxPaginas);

  for (let pagina = 2; pagina <= ultimaPagina; pagina++) {
    const resposta = await getTransferencias(filtros, pagina, TAMANHO_PAGINA_MAXIMO, signal);
    itens.push(...resposta.itens);
  }

  return {
    itens,
    total: primeira.total,
    truncado: primeira.total_paginas > maxPaginas,
  };
}
