

import type { PaginaAtividades } from "../types/api";
import { getJson } from "./apiClient";

export const CAMINHO_ATIVIDADES = "/api/v1/admin/atividades";
export const TAMANHO_PAGINA_ATIVIDADES = 50;

export interface FiltrosAtividades {

  tipo: string;

  usuario: string;
}

export const FILTROS_ATIVIDADES_VAZIOS: FiltrosAtividades = { tipo: "", usuario: "" };

export function listarAtividades(
  filtros: FiltrosAtividades,
  pagina = 1,
  signal?: AbortSignal,
): Promise<PaginaAtividades> {
  return getJson<PaginaAtividades>(CAMINHO_ATIVIDADES, {
    params: {
      tipo: filtros.tipo || undefined,
      usuario: filtros.usuario.trim().slice(0, 100) || undefined,
      pagina: Math.max(1, Math.trunc(pagina)),
      tamanho_pagina: TAMANHO_PAGINA_ATIVIDADES,
    },
    signal,
  });
}
