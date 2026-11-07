

import { ApiError } from "./apiClient";

export type Checagem = (valor: unknown) => boolean;

export function ehObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

export function ehInteiro(valor: unknown): valor is number {
  return typeof valor === "number" && Number.isInteger(valor);
}

export const texto: Checagem = (v) => typeof v === "string";
export const inteiro: Checagem = ehInteiro;
export const booleano: Checagem = (v) => typeof v === "boolean";
export const lista: Checagem = (v) => Array.isArray(v);
export const objeto: Checagem = ehObjeto;
export const ouNulo =
  (checagem: Checagem): Checagem =>
  (v) =>
    v === null || checagem(v);


export function validarFormato<T>(dados: unknown, recurso: string, campos: Record<string, Checagem>): T {
  const problemas = ehObjeto(dados)
    ? Object.entries(campos)
        .filter(([campo, checagem]) => !checagem(dados[campo]))
        .map(([campo]) => campo)
    : ["corpo não é um objeto"];
  if (problemas.length) {
    throw new ApiError(
      `${recurso} veio em formato inesperado (${problemas.join(", ")}). Verifique se frontend e backend estão na mesma versão.`,
      "resposta_invalida",
    );
  }
  return dados as T;
}


export const PAGINACAO: Record<string, Checagem> = {
  total: inteiro,
  pagina: inteiro,
  tamanho_pagina: inteiro,
  total_paginas: inteiro,
  itens: lista,
};
