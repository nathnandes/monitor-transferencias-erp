

import { SEVERIDADES } from "../lib/status";
import type { HealthLive, ParamsResumo, ResumoDashboard } from "../types/api";
import { ApiError, getJson } from "./apiClient";
import { ehInteiro, ehObjeto } from "./validacao";

export const CAMINHO_RESUMO = "/api/v1/dashboard/resumo";
export const CAMINHO_HEALTH_LIVE = "/health/live";


export function validarResumo(dados: unknown): ResumoDashboard {
  const problemas: string[] = [];
  if (!ehObjeto(dados)) {
    problemas.push("corpo não é um objeto");
  } else {
    if (typeof dados.gerado_em !== "string") problemas.push("gerado_em");
    const t = dados.transferencias;
    if (!ehObjeto(t)) problemas.push("transferencias");
    else
      for (const campo of ["total", "processadas", "pendentes", "com_erro"])
        if (!ehInteiro(t[campo])) problemas.push(`transferencias.${campo}`);
    if (!ehInteiro(dados.empresas_ativas)) problemas.push("empresas_ativas");
    if (!ehObjeto(dados.filtro)) problemas.push("filtro");
    const a = dados.situacao_atual;
    if (!ehObjeto(a)) problemas.push("situacao_atual");
    else
      for (const campo of ["pendentes", "pendentes_atrasadas", "com_erro"])
        if (!ehInteiro(a[campo])) problemas.push(`situacao_atual.${campo}`);
    for (const nome of ["periodo", "comparacao"] as const) {
      const f = dados[nome];
      if (f !== null && (!ehObjeto(f) || !["criadas", "processadas", "eventos"].every((c) => ehInteiro(f[c]))))
        problemas.push(nome);
    }
    const s = dados.ultima_sincronizacao;
    if (s !== null && (!ehObjeto(s) || typeof s.status !== "string" || typeof s.inicio !== "string"))
      problemas.push("ultima_sincronizacao");
    const severidades = dados.eventos_por_severidade;

    if (!ehObjeto(severidades) || !SEVERIDADES.every((s) => typeof severidades[s] === "number")) {
      problemas.push("eventos_por_severidade");
    }
    if (!Array.isArray(dados.status_por_empresa)) problemas.push("status_por_empresa");
  }

  if (problemas.length) {
    throw new ApiError(
      `O resumo da API veio em formato inesperado (${problemas.join(", ")}). Verifique se frontend e backend estão na mesma versão.`,
      "resposta_invalida",
    );
  }
  return dados as unknown as ResumoDashboard;
}


export async function getResumoDashboard(params: ParamsResumo = {}, signal?: AbortSignal): Promise<ResumoDashboard> {
  const preenchidos = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
  const dados = await getJson<unknown>(CAMINHO_RESUMO, { params: preenchidos, signal });
  return validarResumo(dados);
}

export function getHealthLive(signal?: AbortSignal): Promise<HealthLive> {
  return getJson<HealthLive>(CAMINHO_HEALTH_LIVE, { signal });
}


export function resumoVazio(resumo: ResumoDashboard): boolean {
  return (
    resumo.transferencias.total === 0 &&
    resumo.empresas_ativas === 0 &&
    resumo.ultima_sincronizacao === null
  );
}
