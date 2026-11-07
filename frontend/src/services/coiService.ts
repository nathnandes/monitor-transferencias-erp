

import type { PaginaTransferencias } from "../types/api";
import { getJson } from "./apiClient";


export const MAXIMO_LISTADAS_NO_AVISO = 5;

export function getTransferenciasSemCoi(signal?: AbortSignal): Promise<PaginaTransferencias> {
  return getJson<PaginaTransferencias>("/api/v1/transferencias", {
    params: { situacao_coi: "ERRADO", pagina: 1, tamanho_pagina: MAXIMO_LISTADAS_NO_AVISO },
    signal,
  });
}
