import type { ReactNode } from "react";

import { formatarNumero, formatarMoedaNumero } from "../../../lib/format";

export interface LinhaTooltipVendas {
  nome: string;
  valor: string;
  cor?: string;
}


export function CaixaTooltipVendas({ titulo, linhas }: { titulo: ReactNode; linhas: LinhaTooltipVendas[] }) {
  return (
    <div className="min-w-44 rounded-lg border border-borda bg-superficie px-3 py-2 text-xs shadow-elevado">
      <p className="mb-1.5 font-semibold text-texto">{titulo}</p>
      {linhas.map((l) => (
        <p key={l.nome} className="flex items-center gap-2 py-0.5 text-texto-2">
          {l.cor && <span aria-hidden className="size-2 rounded-sm" style={{ background: l.cor }} />}
          {l.nome}
          <span className="tabular ml-auto pl-4 font-semibold text-texto">{l.valor}</span>
        </p>
      ))}
    </div>
  );
}

interface PropsTooltip {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }>;
}

interface PontoTooltip {
  faturamento: number;
  notas: number;
  quantidade: number;
  devolucoes?: number | null;
  liquido?: number;
}


export function criarTooltipPonto<T extends PontoTooltip>(
  titulo: (ponto: T) => ReactNode,
  cor: string,
) {
  return function TooltipPonto({ active, payload }: PropsTooltip) {
    const ponto = payload?.[0]?.payload as T | undefined;
    if (!active || !ponto) return null;
    return (
      <CaixaTooltipVendas
        titulo={titulo(ponto)}
        linhas={[
          ...(ponto.devolucoes !== null && ponto.devolucoes !== undefined
            ? [
                { nome: "Faturamento líquido", valor: formatarMoedaNumero((ponto.liquido ?? ponto.faturamento)), cor },
                { nome: "Bruto", valor: formatarMoedaNumero(ponto.faturamento) },
                { nome: "Devoluções", valor: formatarMoedaNumero(ponto.devolucoes) },
              ]
            : [{ nome: "Faturamento", valor: formatarMoedaNumero(ponto.faturamento), cor }]),
          { nome: "Notas", valor: formatarNumero(ponto.notas) },
          { nome: "Quantidade", valor: formatarNumero(Math.round(ponto.quantidade)) },
        ]}
      />
    );
  };
}
