

import { TAMANHO_PAGINA_MAXIMO } from "../../../services/transferenciasService";
import { FILTROS_VAZIOS, type FiltrosTransferencia } from "../../../types/api";

export const TAMANHO_PAGINA_PADRAO = 20;

export const TAMANHOS_PAGINA = [10, 20, 50, 100].filter((n) => n <= TAMANHO_PAGINA_MAXIMO);

export interface ConsultaTransferencias {
  filtros: FiltrosTransferencia;
  pagina: number;
  tamanhoPagina: number;

  detalheId: number | null;
}

export const CONSULTA_INICIAL: ConsultaTransferencias = {
  filtros: FILTROS_VAZIOS,
  pagina: 1,
  tamanhoPagina: TAMANHO_PAGINA_PADRAO,
  detalheId: null,
};

const CAMPOS_FILTRO = Object.keys(FILTROS_VAZIOS) as (keyof FiltrosTransferencia)[];


export const CHAVES_CONSULTA = [...CAMPOS_FILTRO, "pagina", "tamanho_pagina", "detalhe"];


export function normalizarFiltros(filtros: FiltrosTransferencia): FiltrosTransferencia {
  const saida = { ...FILTROS_VAZIOS };
  for (const campo of CAMPOS_FILTRO) saida[campo] = filtros[campo].trim();
  saida.status = saida.status.toUpperCase();
  saida.situacao_coi = saida.situacao_coi.toUpperCase();
  saida.ocorrencia = saida.ocorrencia.toUpperCase();
  return saida;
}


export function linkTransferencias(
  queryGlobal: string,
  filtros: Partial<FiltrosTransferencia>,
  detalheId: number | null = null,
): string {
  const busca = new URLSearchParams(queryGlobal);
  const consulta = consultaParaQuery({
    ...CONSULTA_INICIAL,
    filtros: normalizarFiltros({ ...FILTROS_VAZIOS, ...filtros }),
    detalheId,
  });
  for (const [chave, valor] of new URLSearchParams(consulta)) busca.set(chave, valor);
  const texto = busca.toString();
  return `/transferencias${texto ? `?${texto}` : ""}`;
}


export function filtrosParaParams(filtros: FiltrosTransferencia): Partial<FiltrosTransferencia> {
  const params: Partial<FiltrosTransferencia> = {};
  for (const campo of CAMPOS_FILTRO) {
    const valor = filtros[campo].trim();
    if (valor) params[campo] = valor;
  }
  return params;
}


export function consultaParaQuery(consulta: ConsultaTransferencias): string {
  const busca = new URLSearchParams(filtrosParaParams(consulta.filtros));
  if (consulta.pagina > 1) busca.set("pagina", String(consulta.pagina));
  if (consulta.tamanhoPagina !== TAMANHO_PAGINA_PADRAO) busca.set("tamanho_pagina", String(consulta.tamanhoPagina));
  if (consulta.detalheId !== null) busca.set("detalhe", String(consulta.detalheId));
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

function inteiroPositivo(valor: string | null): number | null {
  if (!valor || !/^\d+$/.test(valor)) return null;
  const n = Number(valor);
  return Number.isSafeInteger(n) && n >= 1 ? n : null;
}


export function queryParaConsulta(search: string): ConsultaTransferencias {
  const busca = new URLSearchParams(search);
  const lidos = { ...FILTROS_VAZIOS };
  for (const campo of CAMPOS_FILTRO) lidos[campo] = busca.get(campo) ?? "";
  const filtros = normalizarFiltros(lidos);

  const tamanho = inteiroPositivo(busca.get("tamanho_pagina"));
  return {
    filtros,
    pagina: inteiroPositivo(busca.get("pagina")) ?? 1,
    tamanhoPagina: tamanho !== null && TAMANHOS_PAGINA.includes(tamanho) ? tamanho : TAMANHO_PAGINA_PADRAO,
    detalheId: inteiroPositivo(busca.get("detalhe")),
  };
}


export function chaveDosFiltros(filtros: FiltrosTransferencia): string {
  return new URLSearchParams(filtrosParaParams(filtros)).toString();
}

export function temFiltro(filtros: FiltrosTransferencia): boolean {
  return CAMPOS_FILTRO.some((campo) => filtros[campo].trim() !== "");
}
