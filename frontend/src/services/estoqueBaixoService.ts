

import type { ParametrosEstoqueBaixo, ParametrosEstoqueBaixoEntrada, SituacaoEstoqueBaixo } from "../types/api";
import { getJson, putJson } from "./apiClient";

export const CAMINHO_ESTOQUE_BAIXO = "/api/v1/admin/estoque-baixo";

export function getEstoqueBaixo(signal?: AbortSignal): Promise<ParametrosEstoqueBaixo> {
  return getJson<ParametrosEstoqueBaixo>(CAMINHO_ESTOQUE_BAIXO, { signal });
}

export function salvarEstoqueBaixo(dados: ParametrosEstoqueBaixoEntrada): Promise<ParametrosEstoqueBaixo> {
  return putJson<ParametrosEstoqueBaixo>(CAMINHO_ESTOQUE_BAIXO, dados);
}


export function getSituacaoEstoqueBaixo(limite = 5, signal?: AbortSignal): Promise<SituacaoEstoqueBaixo> {
  return getJson<SituacaoEstoqueBaixo>(`${CAMINHO_ESTOQUE_BAIXO}/situacao`, { params: { limite }, signal });
}
