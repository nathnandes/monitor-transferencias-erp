

import { ABAS, ehAba } from "../../../routes/abas";
import type { EmpresaResumo } from "../../../types/api";

export function paraNumero(valor: string | null | undefined): number {
  const n = Number(valor);
  return Number.isFinite(n) ? n : 0;
}

export function participacao(valor: number, total: number): number {
  return total > 0 ? (valor / total) * 100 : 0;
}

const PERCENTUAL = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function formatarPercentual(valor: number): string {
  return `${PERCENTUAL.format(valor)}%`;
}


export function nomeForma(forma: string): string {
  const texto = forma.trim().toLowerCase();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

const PREFIXO_LOJA = "VENDAS.EMPRESA_";


export function lojasQueVendem(
  empresas: EmpresaResumo[] | null,
): EmpresaResumo[] {
  if (empresas)
    return empresas.filter(
      (e) => e.codigo !== "" && ehAba(`${PREFIXO_LOJA}${Number(e.codigo)}`),
    );
  return ABAS.filter((a) => a.aba.startsWith(PREFIXO_LOJA)).map((a) => {
    const codigo = a.aba.slice(PREFIXO_LOJA.length);
    return { id: Number(codigo), codigo, nome: a.rotulo };
  });
}
