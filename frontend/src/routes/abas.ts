import { MARCA } from "../lib/marca";

import type { Aba, Modulo } from "../types/auth";

export interface InfoAba {
  aba: Aba;
  modulo: Modulo;
  rotulo: string;

  rota: string;

  pai?: Aba;
}


const POR_ABA = {
  "DASHBOARD.TV": { modulo: "DASHBOARD", rotulo: "Modo TV", rota: "/tv" },
  "TRANSFERENCIAS.CONTROLE": { modulo: "TRANSFERENCIAS", rotulo: "Controle", rota: "/transferencias/controle" },
  "ESTOQUE.SALDOS": { modulo: "ESTOQUE", rotulo: "Saldos", rota: "/estoque?aba=saldos" },
  "ESTOQUE.LOJA": { modulo: "ESTOQUE", rotulo: "Loja", rota: "/estoque?aba=loja" },
  "ESTOQUE.LIVRO": { modulo: "ESTOQUE", rotulo: "Entradas e saídas", rota: "/estoque?aba=livro" },
  "ESTOQUE.BALANCO": { modulo: "ESTOQUE", rotulo: "Balanço", rota: "/estoque?aba=balanco" },
  "ESTOQUE.AVULSAS": { modulo: "ESTOQUE", rotulo: "Avulsas", rota: "/estoque?aba=avulsas" },
  "ESTOQUE.JUSTIFICATIVAS": {
    modulo: "ESTOQUE",
    rotulo: "Justificativas (dentro de Avulsas)",
    rota: "/estoque?aba=avulsas",
    pai: "ESTOQUE.AVULSAS",
  },
  "VENDAS.TV": { modulo: "VENDAS", rotulo: "Modo TV", rota: "/vendas/tv" },

  "VENDAS.GERAL": { modulo: "VENDAS", rotulo: "Geral (todas as lojas)", rota: "/vendas" },
  "VENDAS.EMPRESA_1": { modulo: "VENDAS", rotulo: MARCA.lojas["1"], rota: "/vendas?empresa=1" },
  "VENDAS.EMPRESA_2": { modulo: "VENDAS", rotulo: MARCA.lojas["2"], rota: "/vendas?empresa=2" },
  "VENDAS.EMPRESA_3": { modulo: "VENDAS", rotulo: MARCA.lojas["3"], rota: "/vendas?empresa=3" },
  "VENDAS.EMPRESA_6": { modulo: "VENDAS", rotulo: MARCA.lojas["6"], rota: "/vendas?empresa=6" },
} satisfies Record<Aba, Omit<InfoAba, "aba">>;

export const ABAS: InfoAba[] = Object.entries(POR_ABA).map(([aba, info]) => ({ aba: aba as Aba, ...info }));

export function infoAba(aba: Aba): InfoAba {
  return { aba, ...POR_ABA[aba] };
}

export function ehAba(valor: string): valor is Aba {
  return valor in POR_ABA;
}


export function abaLiberada(aba: Aba, modulos: readonly Modulo[], abas: readonly Aba[] | null): boolean {
  return modulos.includes(POR_ABA[aba].modulo) && (abas === null || abas.includes(aba));
}
