

import { ehDataValida } from "./datas";
import { PERIODOS, type Periodo } from "./periodo";

export interface FiltroGlobal {

  empresa: string;
  periodo: Periodo;

  dataInicial: string;
  dataFinal: string;
}

export const PERIODO_PADRAO: Periodo = "hoje";

export const FILTRO_GLOBAL_PADRAO: FiltroGlobal = {
  empresa: "",
  periodo: PERIODO_PADRAO,
  dataInicial: "",
  dataFinal: "",
};


export const CHAVES_FILTRO_GLOBAL = ["empresa", "periodo", "data_inicial", "data_final"] as const;

const VALORES_PERIODO = new Set<string>(PERIODOS.map((p) => p.valor));

export function lerFiltroGlobal(search: string): FiltroGlobal {
  const busca = new URLSearchParams(search);
  const empresa = (busca.get("empresa") ?? "").trim();
  let dataInicial = busca.get("data_inicial") ?? "";
  let dataFinal = busca.get("data_final") ?? "";
  if (!ehDataValida(dataInicial)) dataInicial = "";
  if (!ehDataValida(dataFinal)) dataFinal = "";
  if (dataInicial && dataFinal && dataInicial > dataFinal) dataFinal = "";

  const bruto = busca.get("periodo") ?? "";
  let periodo: Periodo;
  if (VALORES_PERIODO.has(bruto)) periodo = bruto as Periodo;
  else periodo = dataInicial || dataFinal ? "personalizado" : PERIODO_PADRAO;

  if (periodo !== "personalizado") {
    dataInicial = "";
    dataFinal = "";
  }
  return { empresa, periodo, dataInicial, dataFinal };
}


export function escreverFiltroGlobal(busca: URLSearchParams, filtro: FiltroGlobal): URLSearchParams {
  for (const chave of CHAVES_FILTRO_GLOBAL) busca.delete(chave);
  if (filtro.empresa) busca.set("empresa", filtro.empresa);
  if (filtro.periodo !== PERIODO_PADRAO) busca.set("periodo", filtro.periodo);
  if (filtro.periodo === "personalizado") {
    if (filtro.dataInicial) busca.set("data_inicial", filtro.dataInicial);
    if (filtro.dataFinal) busca.set("data_final", filtro.dataFinal);
  }
  return busca;
}


export function queryDoFiltroGlobal(filtro: FiltroGlobal): string {
  const texto = escreverFiltroGlobal(new URLSearchParams(), filtro).toString();
  return texto ? `?${texto}` : "";
}
