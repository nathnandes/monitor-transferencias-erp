

import type { PaginaAlertas, ParamsAlertas, ResumoAlertas } from "../types/api";
import { getJson } from "./apiClient";


export const TAMANHO_PAGINA_MAXIMO = 100;

export function getAlertas(
  filtros: ParamsAlertas,
  pagina = 1,
  tamanhoPagina = 20,
  signal?: AbortSignal,
): Promise<PaginaAlertas> {
  const tamanho = Math.min(Math.max(1, Math.trunc(tamanhoPagina)), TAMANHO_PAGINA_MAXIMO);
  return getJson<PaginaAlertas>("/api/v1/alertas", {
    params: { ...filtros, pagina: Math.max(1, Math.trunc(pagina)), tamanho_pagina: tamanho },
    signal,
  });
}

export function getResumoAlertas(signal?: AbortSignal): Promise<ResumoAlertas> {
  return getJson<ResumoAlertas>("/api/v1/alertas/resumo", { signal });
}
