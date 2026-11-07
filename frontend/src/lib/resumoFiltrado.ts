

import type { EstadoFiltroGlobal } from "../hooks/useFiltroGlobal";
import { calcularVariacao, type Sentido, type Variacao } from "./variacao";
import type { Fluxo, ParamsResumo, ResumoDashboard } from "../types/api";

export function paramsDoResumo({ filtro, intervalo, comparacao }: Pick<EstadoFiltroGlobal, "filtro" | "intervalo" | "comparacao">): ParamsResumo {
  return {
    empresa: filtro.empresa || undefined,
    data_inicial: intervalo?.inicio,
    data_final: intervalo?.fim,
    comparar_inicial: comparacao?.inicio,
    comparar_final: comparacao?.fim,
  };
}

export interface VariacaoRotulada {
  valor: Variacao;
  rotulo: string;
}


export function variacaoDoFluxo(
  resumo: ResumoDashboard | null,
  campo: keyof Fluxo,
  rotulo: string | undefined,
  sentido: Sentido,
): VariacaoRotulada | null {
  if (!resumo?.periodo || !resumo.comparacao || !rotulo) return null;
  return { valor: calcularVariacao(resumo.periodo[campo], resumo.comparacao[campo], rotulo, sentido), rotulo };
}


export function descreverEscopo(descricaoPeriodo: string, resumo: ResumoDashboard | null, codigoEmpresa: string): string {
  const empresa = resumo?.filtro.empresa ?? null;
  const nome = empresa ? `Empresa ${empresa.codigo}` : codigoEmpresa ? `Empresa ${codigoEmpresa}` : "consolidado";
  return `${descricaoPeriodo} · ${nome}`;
}
