

import type {
  LimitesPendencia,
  NovosLimitesPendencia,
  PainelAnomalias,
  PainelControle,
  PrazoRota,
  PrazosRota,
  SituacaoTratativa,
  TratativaRegistrada,
} from "../types/api";
import { getJson, postJson, putJson } from "./apiClient";
import { lista, objeto, validarFormato } from "./validacao";

export interface ParamsControle {
  empresa?: string;
  data_inicial?: string;
  data_final?: string;
}

export function getPainelControle(params: ParamsControle, signal?: AbortSignal): Promise<PainelControle> {
  return getJson<unknown>("/api/v1/transferencias/controle", { params: { ...params }, signal }).then((dados) =>
    validarFormato<PainelControle>(dados, "O painel de controle", {
      resumo: objeto,
      em_transito: lista,
      rotas: lista,
      divergencias: lista,
      fiscal: lista,
      emissores: lista,
    }),
  );
}

export function getAnomalias(params: ParamsControle, signal?: AbortSignal): Promise<PainelAnomalias> {
  return getJson<unknown>("/api/v1/transferencias/anomalias", { params: { ...params }, signal }).then((dados) =>
    validarFormato<PainelAnomalias>(dados, "O painel de anomalias", { lista }),
  );
}

export function getPrazos(signal?: AbortSignal): Promise<PrazosRota> {
  return getJson<PrazosRota>("/api/v1/transferencias/prazos", { signal });
}


export function salvarPrazos(prazos: PrazoRota[]): Promise<PrazosRota> {
  return putJson<PrazosRota>("/api/v1/transferencias/prazos", prazos);
}

export function getLimites(signal?: AbortSignal): Promise<LimitesPendencia> {
  return getJson<LimitesPendencia>("/api/v1/transferencias/limites", { signal });
}


export function salvarLimites(limites: NovosLimitesPendencia): Promise<LimitesPendencia> {
  return putJson<LimitesPendencia>("/api/v1/transferencias/limites", limites);
}

export function getTratativas(id: number, signal?: AbortSignal): Promise<TratativaRegistrada[]> {
  return getJson<TratativaRegistrada[]>(`/api/v1/transferencias/${id}/tratativas`, { signal });
}

export function registrarTratativa(
  id: number,
  dados: { situacao: SituacaoTratativa; observacao: string },
): Promise<TratativaRegistrada> {
  return postJson<TratativaRegistrada>(`/api/v1/transferencias/${id}/tratativas`, dados);
}
