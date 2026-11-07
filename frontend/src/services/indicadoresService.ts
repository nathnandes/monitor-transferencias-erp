

import type { IndicadoresPorEmpresa, ParamsIndicadores } from "../types/api";
import { ApiError, getJson } from "./apiClient";

export const CAMINHO_INDICADORES = "/api/v1/dashboard/indicadores-empresas";


export function validarIndicadores(dados: unknown): IndicadoresPorEmpresa {
  const d = dados as Partial<IndicadoresPorEmpresa> | null;
  const ok =
    typeof d === "object" &&
    d !== null &&
    typeof d.granularidade === "string" &&
    Array.isArray(d.empresas) &&
    d.empresas.every((e) => typeof e?.empresa?.codigo === "string" && Array.isArray(e.serie) && typeof e.totais === "object");
  if (!ok) {
    throw new ApiError(
      "Os indicadores por empresa vieram em formato inesperado. Verifique se frontend e backend estão na mesma versão.",
      "resposta_invalida",
    );
  }
  return d as IndicadoresPorEmpresa;
}


export async function getIndicadoresEmpresas(params: ParamsIndicadores = {}, signal?: AbortSignal): Promise<IndicadoresPorEmpresa> {
  const preenchidos = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
  const dados = await getJson<unknown>(CAMINHO_INDICADORES, { params: preenchidos, signal });
  return validarIndicadores(dados);
}
